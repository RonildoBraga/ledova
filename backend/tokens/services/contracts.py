from django.conf import settings

from tokens.models import ShareToken, Stablecoin

CONTRACT_SETTINGS = (
    "WHITELIST_CONTRACT_ADDRESS",
    "SHARE_TOKEN_FACTORY_ADDRESS",
    "ATOMIC_SWAP_ADDRESS",
    "STABLECOIN_CONTRACT_ADDRESS",
    "SHARE_EXCHANGE_ADDRESS",
)


def known_contract_addresses() -> set[str]:
    """Lower-cased addresses a broadcast transaction may target: configured contracts plus every token contract."""
    addresses = [getattr(settings, name, "") for name in CONTRACT_SETTINGS]
    addresses += ShareToken.objects.filter(contract_address__isnull=False).values_list("contract_address", flat=True)
    addresses += Stablecoin.objects.filter(is_active=True).values_list("contract_address", flat=True)
    return {address.lower() for address in addresses if address}
