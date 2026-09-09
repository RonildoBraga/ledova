from django.db.models import Q, QuerySet
from django.db.models.functions import Lower

from shared.constants import BLOCKCHAIN_BASE


class WhitelistEntryQuerySet(QuerySet):

    def for_registry(self):
        return self.filter(Q(wallet__chain=BLOCKCHAIN_BASE) | Q(wallet__isnull=True))

    def filter_by_address(self, address):
        if address:
            return self.for_registry().filter(Q(wallet__address__iexact=address) | Q(address__iexact=address))
        return self.none()

    def for_addresses(self, addresses):
        keys = sorted({(address or "").strip().lower() for address in addresses} - {""})
        if not keys:
            return self.none()
        return (
            self.for_registry()
            .annotate(registry_wallet_address=Lower("wallet__address"), registry_address=Lower("address"))
            .filter(Q(registry_wallet_address__in=keys) | Q(registry_address__in=keys))
        )

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

    def failed_with_a_sent_add(self):
        from whitelist.models import WhitelistStatus

        return self.filter(status=WhitelistStatus.FAILED, failure_reconciled_at__isnull=True).exclude(
            add_tx_hash__isnull=True
        )
