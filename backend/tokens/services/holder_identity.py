from wallets.models import Wallet
from whitelist.services.identity import ADDRESS_SEPARATOR, NAME_SEPARATOR, profile_name


class StampedIdentity:
    def __init__(self, name: str = "", residential_address: str = ""):
        self.name = name
        self.residential_address = residential_address

    def __bool__(self):
        return bool(self.name or self.residential_address)


def identity_at_allotment(address: str) -> StampedIdentity:
    wallets = list(Wallet.objects.filter_by_address(address).order_by("uuid")[:2])
    if len(wallets) != 1 or wallets[0].user_account_id is None:
        return StampedIdentity()

    profiles = list(wallets[0].user_account.user_profiles.all())
    names = [profile_name(profile) for profile in profiles]
    addresses = [(profile.residential_address or "").strip() for profile in profiles]

    return StampedIdentity(
        NAME_SEPARATOR.join(name for name in names if name),
        ADDRESS_SEPARATOR.join(address for address in addresses if address),
    )
