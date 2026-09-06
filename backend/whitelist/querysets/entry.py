from django.db.models import Q, QuerySet
from web3 import Web3


def address_variants(addresses) -> list:
    variants = set()
    for address in addresses:
        candidate = (address or "").strip()
        if not candidate:
            continue
        variants.update({candidate, candidate.lower()})
        if Web3.is_address(candidate):
            variants.add(Web3.to_checksum_address(candidate))
    return sorted(variants)


class WhitelistEntryQuerySet(QuerySet):

    def filter_by_address(self, address):
        if address:
            return self.filter(Q(wallet__address__iexact=address) | Q(address__iexact=address))
        return self

    def for_addresses(self, addresses):
        variants = address_variants(addresses)
        if not variants:
            return self.none()
        return self.filter(Q(wallet__address__in=variants) | Q(address__in=variants))

    def with_holder_identity(self):
        return self.select_related("wallet__user_account").prefetch_related("wallet__user_account__user_profiles__user")

    def visible_to_user(self, user):
        if user is not None and user.is_authenticated and user.is_staff:
            return self
        return self.none()

    def active(self):
        from whitelist.models import WhitelistStatus

        return self.filter(status=WhitelistStatus.ACTIVE)

    def pending(self):
        from whitelist.models import WhitelistStatus

        return self.filter(status=WhitelistStatus.PENDING)
