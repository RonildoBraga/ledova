from django.conf import settings

from assets.models import AssetChainDeployment, AssetType
from tokens.models import ShareToken

CONTRACT_SETTINGS = (
    "WHITELIST_CONTRACT_ADDRESS",
    "SHARE_TOKEN_FACTORY_ADDRESS",
    "ATOMIC_SWAP_ADDRESS",
    "STABLECOIN_CONTRACT_ADDRESS",
    "SHARE_EXCHANGE_ADDRESS",
)


def known_contract_addresses() -> set[str]:
    addresses = [getattr(settings, name, "") for name in CONTRACT_SETTINGS]
    addresses += ShareToken.objects.filter(contract_address__isnull=False).values_list("contract_address", flat=True)
    addresses += AssetChainDeployment.objects.filter(
        asset__asset_type=AssetType.STABLECOIN.value, asset__is_active=True, is_active=True
    ).values_list("contract_address", flat=True)
    return {address.lower() for address in addresses if address}
