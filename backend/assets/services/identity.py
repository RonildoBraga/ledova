"""Which Asset row a chain transfer belongs to: (chain, contract) for tokens, the chain's native coin otherwise."""

import logging
from typing import Optional

from django.db import transaction

from assets.models import Asset, AssetChainDeployment, AssetType
from assets.services.sync import SUPPORTED_ASSETS
from shared.constants import CHAIN_TO_NATIVE_ASSET, get_native_asset_symbol

logger = logging.getLogger(__name__)

SYMBOL_MAX_LENGTH = Asset._meta.get_field("symbol").max_length
SUFFIX_HEX_CHARS = 6
RESERVED_SYMBOLS = frozenset(symbol.upper() for symbol in (*SUPPORTED_ASSETS, *CHAIN_TO_NATIVE_ASSET.values()))


def native_asset_for_chain(chain: str) -> Asset:
    """The chain's native coin; before the seed has run, a native_crypto row under the native symbol.

    A row that owns the native symbol but is not the native coin (a quarantined token can never
    take it, see RESERVED_SYMBOLS, so only hand-entered data) refuses the transfer with ValueError.
    """
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
    """Record a contract the allowlist does not know as an unverified Asset plus its deployment.

    Identity is (chain, contract address), never the declared symbol, so the deployment is looked
    up before any symbol logic and a row that does not carry it is never returned:
    - a deployment of this contract on this chain that an operator switched off refuses the
      transfer (ValueError; the wallet sync skips and logs it) instead of resolving to its row;
    - the same address on another chain is another contract (same-address contracts on other
      EVM chains are attacker-reachable through deterministic deployers and pre-EIP-155 replay)
      and gets its own unverified row; an operator adds a second chain's deployment by hand;
    - otherwise a new unverified row is created under a symbol no other row owns, compared
      case-insensitively: the declared symbol, else the symbol plus a hex prefix of the contract
      that grows until it is free.
    Neither a fake "USDC", "usdc" nor "USDC-a0b866" can therefore book against someone else's
    row, whichever of the two contracts the chain shows first. Unverified rows stay hidden from
    every customer read until an operator marks them verified. Every SUPPORTED_ASSETS symbol and
    every chain's native symbol counts as taken even before ensure_supported_assets has seeded
    it, so the seed's update_or_create(symbol=...) and native_asset_for_chain can never land on
    a quarantined row.
    """
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
        unique_symbol = _free_symbol(declared, contract_address)
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


def _free_symbol(declared: str, contract_address: str) -> str:
    """The declared symbol when no row owns it (case-insensitively), else declared-<hex prefix of
    the contract> with the prefix growing one character at a time until the symbol is free; the
    declared part is trimmed to fit. Raises ValueError when even the longest prefix that fits is
    taken."""
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
