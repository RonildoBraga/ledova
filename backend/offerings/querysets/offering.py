from django.db.models import (
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone


class OfferingQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        return self.filter(token__company__in=Company.objects.visible_to_user(user))

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        return self.filter(token__company__in=Company.objects.manageable_by_user(user))

    def live(self):
        from offerings.models.offering import LIVE_OFFERING_STATUSES

        return self.filter(status__in=LIVE_OFFERING_STATUSES)

    def open_now(self):
        from offerings.models.offering import OfferingStatus

        now = timezone.now()
        return self.filter(status=OfferingStatus.APPROVED, opens_at__lte=now).filter(
            Q(closes_at__isnull=True) | Q(closes_at__gt=now)
        )

    def awaiting_review(self):
        from offerings.models.offering import OfferingStatus

        return self.filter(status__in=[OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW])

    def with_subscribed_shares(self):
        from offerings.models import Subscription

        subscribed = (
            Subscription.objects.paid_or_allotted()
            .filter(offering=OuterRef("pk"))
            .values("offering")
            .annotate(total=Sum(Coalesce("allotted_quantity", "quantity")))
            .values("total")
        )
        return self.annotate(
            subscribed_shares=Coalesce(
                Subquery(subscribed, output_field=IntegerField()), Value(0), output_field=IntegerField()
            )
        )

    def cap_reached(self):
        return self.open_now().with_subscribed_shares().filter(subscribed_shares__gte=F("cap_shares"))

    def for_token(self, token):
        return self.filter(token=token)

    def with_relations(self):
        return self.select_related("token", "token__company", "submitted_by", "reviewed_by")
