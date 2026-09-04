from dataclasses import dataclass
from uuid import UUID

from django.db.models import Q
from rest_framework.exceptions import NotFound
from web3 import Web3

from wallets.models import Wallet


@dataclass(frozen=True)
class AuthorizedEVMWallets:
    addresses: tuple[str, ...]
    wallet_ids: tuple[UUID, ...]


def resolve_verified_evm_wallets(user, requested_addresses: list[str]) -> AuthorizedEVMWallets:
    """Resolve caller-visible verified EVM wallets without leaking misses."""
    address_keys = []
    address_query = Q()

    for requested_address in requested_addresses:
        address = requested_address.strip()
        if not Web3.is_address(address):
            raise NotFound("Wallet not found.")

        address_key = address.lower()
        if address_key in address_keys:
            continue

        address_keys.append(address_key)
        address_query |= Q(address__iexact=address)

    if not address_keys:
        raise NotFound("Wallet not found.")

    wallets = list(
        Wallet.objects.visible_to_user(user)
        .verified_evm()
        .filter(address_query)
        .only("uuid", "address")
        .order_by("uuid")
    )

    wallets_by_address = {}
    for wallet in wallets:
        wallets_by_address.setdefault(wallet.address.lower(), []).append(wallet)

    if any(address_key not in wallets_by_address for address_key in address_keys):
        raise NotFound("Wallet not found.")

    return AuthorizedEVMWallets(
        addresses=tuple(Web3.to_checksum_address(address_key) for address_key in address_keys),
        wallet_ids=tuple(wallet.uuid for wallet in wallets),
    )
