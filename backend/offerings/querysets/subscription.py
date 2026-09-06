from django.db.models import QuerySet, Sum


class SubscriptionQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_account__user_profiles__user=user)

    def for_offering(self, offering):
        return self.filter(offering=offering)

    def paid(self):
        from offerings.models.subscription import SubscriptionStatus

        return self.filter(status=SubscriptionStatus.PAID)

    def awaiting_allotment(self):
        return self.paid().filter(issuance_request__isnull=True)

    def committed_to_shares(self):
        from offerings.models.subscription import SubscriptionStatus

        return self.filter(status__in=[SubscriptionStatus.PAID, SubscriptionStatus.ALLOTTED]).exclude(
            issuance_request__isnull=True
        )

    def executed_but_not_allotted(self):
        from tokens.models import RequestStatus

        return self.paid().filter(issuance_request__status=RequestStatus.EXECUTED)

    def unpaid_past_due(self, moment):
        from offerings.models.subscription import SubscriptionStatus

        return self.filter(
            status=SubscriptionStatus.AWAITING_PAYMENT,
            amount_received__isnull=True,
            payment_due_at__isnull=False,
            payment_due_at__lt=moment,
        )

    def share_commitment(self) -> int:
        from django.db.models.functions import Coalesce

        total = self.aggregate(total=Coalesce(Sum(Coalesce("allotted_quantity", "quantity")), 0))
        return int(total["total"])

    def with_relations(self):
        return self.select_related(
            "offering",
            "offering__token",
            "offering__token__company",
            "user_account",
            "wallet",
            "settlement_asset",
            "issuance_request",
        )
