from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone


class WhitelistEntryQuerySet(QuerySet):

    def filter_by_status(self, status):
        if status:
            return self.filter(status=status)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        queryset = self
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        return queryset

    def filter_by_is_whitelisted(self, is_whitelisted):
        if is_whitelisted is not None:
            return self.filter(is_whitelisted=is_whitelisted)
        return self

    def filter_by_uuid(self, uuid):
        if uuid:
            return self.filter(uuid=uuid)
        return self

    def filter_by_address(self, address):
        if address:
            return self.filter(wallet__address__iexact=address)
        return self

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return self.none()

    def with_optimized_data(self):
        return self.select_related("wallet")

    def active(self):
        from whitelist.models import WhitelistStatus

        return self.filter(status=WhitelistStatus.ACTIVE)

    def pending(self):
        from whitelist.models import WhitelistStatus

        return self.filter(status=WhitelistStatus.PENDING)

    def failed(self):
        from whitelist.models import WhitelistStatus

        return self.filter(status=WhitelistStatus.FAILED)

    def on_chain(self):
        return self.filter(is_whitelisted=True)

    def needs_sync(self):
        stale_cutoff = timezone.now() - timedelta(hours=1)
        return self.filter(Q(last_synced_at__isnull=True) | Q(last_synced_at__lt=stale_cutoff))

    def search(self, query):
        if not query:
            return self
        return self.filter(wallet__address__icontains=query)
