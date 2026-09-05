import logging
from typing import Optional

from django.db import transaction

from assets.models import Asset, AssetChainDeployment, AssetType
from assets.services.sync import SUPPORTED_ASSETS
from shared.constants import CHAIN_TO_NATIVE_ASSET, get_native_asset_symbol

logger = logging.getLogger(__name__)

SYMBOL_MAX_LENGTH = Asset._meta.get_field("symbol").max_length
NAME_MAX_LENGTH = Asset._meta.get_field("name").max_length
SUFFIX_HEX_CHARS = 6
RESERVED_SYMBOLS = frozenset(symbol.upper() for symbol in (*SUPPORTED_ASSETS, *CHAIN_TO_NATIVE_ASSET.values()))


def native_asset_for_chain(chain: str) -> Asset:
    asset = Asset.objects.native_for_chain(chain)
    if asset is None:
        symbol = get_native_asset_symbol(chain)
        asset, _ = Asset.objects.get_or_create(
            symbol=symbol, defaults={"name": symbol, "asset_type": AssetType.NATIVE_CRYPTO.value}
        )
        if asset.asset_type != AssetType.NATIVE_CRYPTO.value:
            raise ValueError(f"Symbol {symbol} belongs to a {asset.asset_type} row, not the native coin of {chain}")
    return asset


def quarantine_unknown_token(
    chain: str, contract_address: str, symbol: Optional[str], decimals: Optional[int]
) -> Asset:
    deployment = (
        AssetChainDeployment.objects.select_related("asset")
        .filter(chain=chain, contract_address__iexact=contract_address)
        .first()
    )
    if deployment is not None:
        if not deployment.is_active:
            raise ValueError(f"Deployment of {contract_address} on {chain} is switched off; transfer not booked")
        return deployment.asset

    decimals = decimals or 18
    declared = ((symbol or "").strip() or "UNKNOWN")[:SYMBOL_MAX_LENGTH]
    with transaction.atomic():
        unique_symbol = free_symbol(declared, contract_address)
        asset = Asset.objects.create(
            symbol=unique_symbol,
            name=declared,
            asset_type=AssetType.ERC20_TOKEN.value,
            decimals=decimals,
            is_verified=False,
        )
        AssetChainDeployment.objects.create(
            asset=asset, chain=chain, contract_address=contract_address, decimals=decimals
        )
    logger.info(f"Quarantined unknown token {unique_symbol} ({contract_address[:10]}...) on {chain}")
    return asset


def free_symbol(declared: str, contract_address: str) -> str:
    hex_part = (contract_address[2:] if contract_address[:2].lower() == "0x" else contract_address).lower()
    longest = min(len(hex_part), SYMBOL_MAX_LENGTH - 1)
    candidate = declared
    length = SUFFIX_HEX_CHARS
    while candidate.upper() in RESERVED_SYMBOLS or Asset.objects.filter(symbol__iexact=candidate).exists():
        if length > longest:
            raise ValueError(f"No free symbol for {contract_address}: every suffix of {declared} is taken")
        suffix = "-" + hex_part[:length]
        candidate = declared[: max(0, SYMBOL_MAX_LENGTH - len(suffix))] + suffix
        length += 1
    return candidate


def verified_contract_asset(
    chain: str, contract_address: str, symbol: str, name: str, decimals: int, asset_type: str
) -> Asset:
    deployment = (
        AssetChainDeployment.objects.select_related("asset")
        .filter(chain=chain, contract_address__iexact=contract_address)
        .first()
    )
    name = name[:NAME_MAX_LENGTH]
    if deployment is not None:
        return _adopt_deployment(deployment, name, decimals, asset_type)

    with transaction.atomic():
        asset = Asset.objects.create(
            symbol=free_symbol(symbol[:SYMBOL_MAX_LENGTH], contract_address),
            name=name,
            asset_type=asset_type,
            decimals=decimals,
            is_verified=True,
        )
        AssetChainDeployment.objects.create(
            asset=asset, chain=chain, contract_address=contract_address, decimals=decimals
        )
    logger.info(f"Verified {asset.symbol} ({contract_address[:10]}...) on {chain} as a {asset_type}")
    return asset


def _adopt_deployment(deployment: AssetChainDeployment, name: str, decimals: int, asset_type: str) -> Asset:
    asset = deployment.asset
    changed = [
        field
        for field, value in (("name", name), ("asset_type", asset_type), ("decimals", decimals), ("is_verified", True))
        if getattr(asset, field) != value
    ]
    if changed:
        asset.name = name
        asset.asset_type = asset_type
        asset.decimals = decimals
        asset.is_verified = True
        asset.save(update_fields=[*changed, "updated_at"])
        logger.info(f"Adopted {asset.symbol} on {deployment.chain} as a verified {asset_type}: {', '.join(changed)}")
    if deployment.decimals != decimals:
        deployment.decimals = decimals
        deployment.save(update_fields=["decimals", "updated_at"])
    return asset
