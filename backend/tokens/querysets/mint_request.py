from django.db.models import Q, QuerySet


class MintRequestQuerySet(QuerySet):

    def filter_by_recipient_address(self, recipient_address):
        if recipient_address:
            return self.filter(recipient_address__iexact=recipient_address)
        return self

    def filter_by_recipient_addresses(self, recipient_addresses):
        """Complex: OR query across multiple addresses (case-insensitive)."""
        if recipient_addresses:
            q = Q()
            for addr in recipient_addresses:
                q |= Q(recipient_address__iexact=addr)
            return self.filter(q)
        return self

    def stablecoin_mints(self):
        return self.filter(stablecoin__isnull=False)

    def yield_token_mints(self):
        return self.filter(yield_token__isnull=False)

    def executed(self):
        from tokens.models.mint_request import MintRequestStatus

        return self.filter(status=MintRequestStatus.EXECUTED, transaction__isnull=False)

    def pending(self):
        from tokens.models.mint_request import MintRequestStatus

        return self.filter(status=MintRequestStatus.PENDING)

    def approved(self):
        from tokens.models.mint_request import MintRequestStatus

        return self.filter(status=MintRequestStatus.APPROVED)

    def actionable(self):
        from tokens.models.mint_request import MintRequestStatus

        return self.filter(status__in=[MintRequestStatus.PENDING, MintRequestStatus.APPROVED])

    def with_related(self):
        return self.select_related("stablecoin", "yield_token", "transaction", "requested_by", "executed_by")

    def with_token(self):
        return self.select_related("stablecoin", "yield_token", "transaction")
