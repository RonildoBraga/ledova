from django.db.models import Q, QuerySet
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

    def for_token(self, token):
        return self.filter(token=token)

    def with_relations(self):
        return self.select_related("token", "token__company", "submitted_by", "reviewed_by")
