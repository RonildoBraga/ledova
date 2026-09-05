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
RESERVED_SYMBOLS = frozenset(SUPPORTED_ASSETS) | frozenset(CHAIN_TO_NATIVE_ASSET.values())


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

    Identity is the contract address, never the declared symbol, so the contract is looked up
    before any symbol logic and a row that does not carry it is never returned:
    - a deployment of this contract on this chain that an operator switched off refuses the
      transfer (ValueError; the wallet sync skips and logs it) instead of resolving to its row;
    - the same contract already known on another chain joins that row with a deployment here
      only while the row is UNVERIFIED and that deployment is active: a verified row never gains
      a deployment without an operator (same-address contracts on other EVM chains are
      attacker-reachable through deterministic deployers and pre-EIP-155 replay), and a
      deployment an operator switched off is not undone by the address turning up elsewhere;
    - otherwise a new unverified row is created under a symbol no other row owns: the declared
      symbol, else the symbol plus a hex prefix of the contract that grows until it is free.
    Neither a fake "USDC" nor a fake "USDC-a0b866" can therefore book against someone else's
    row, whichever of the two contracts the chain shows first. Unverified rows stay hidden from
    every customer read until an operator marks them verified. Every SUPPORTED_ASSETS symbol and
    every chain's native symbol counts as taken even before ensure_supported_assets has seeded
    it, so the seed's update_or_create(symbol=...) and native_asset_for_chain can never land on
    a quarantined row.
    """
    deployments = AssetChainDeployment.objects.select_related("asset").filter(contract_address__iexact=contract_address)
    on_this_chain = deployments.filter(chain=chain).first()
    if on_this_chain is not None:
        if not on_this_chain.is_active:
            raise ValueError(f"Deployment of {contract_address} on {chain} is switched off; transfer not booked")
        return on_this_chain.asset

    decimals = decimals or 18
    elsewhere = deployments.filter(asset__is_verified=False, is_active=True).first()
    if elsewhere is not None:
        AssetChainDeployment.objects.create(
            asset=elsewhere.asset, chain=chain, contract_address=contract_address, decimals=decimals
        )
        logger.info(
            f"Contract {contract_address[:10]}... already {elsewhere.asset.symbol} on {elsewhere.chain}; added {chain}"
        )
        return elsewhere.asset

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
    """The declared symbol when no row owns it, else declared-<hex prefix of the contract> with the
    prefix growing one character at a time until the symbol is free; the declared part is trimmed
    to fit. Raises ValueError when even the longest prefix that fits is taken."""
    hex_part = (contract_address[2:] if contract_address[:2].lower() == "0x" else contract_address).lower()
    longest = min(len(hex_part), SYMBOL_MAX_LENGTH - 1)
    candidate = declared
    length = SUFFIX_HEX_CHARS
    while candidate in RESERVED_SYMBOLS or Asset.objects.filter(symbol=candidate).exists():
        if length > longest:
            raise ValueError(f"No free symbol for {contract_address}: every suffix of {declared} is taken")
        suffix = "-" + hex_part[:length]
        candidate = declared[: max(0, SYMBOL_MAX_LENGTH - len(suffix))] + suffix
        length += 1
    return candidate
