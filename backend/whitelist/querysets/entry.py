from django.db.models import QuerySet


class WhitelistEntryQuerySet(QuerySet):

    def filter_by_address(self, address):
        if address:
            return self.filter(wallet__address__iexact=address)
        return self

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
