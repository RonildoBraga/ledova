from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone


class InvestorClassificationQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_account__user_profiles__user=user)

    def manageable_by_user(self, user):
        return self.visible_to_user(user).submitted()

    def submitted(self):
        from users.models.investor_classification import InvestorClassificationStatus

        return self.filter(status=InvestorClassificationStatus.SUBMITTED)

    def live(self):
        from users.models.investor_classification import InvestorClassificationStatus

        return self.filter(status=InvestorClassificationStatus.VERIFIED).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )

    def evidence_purgeable(self, moment):
        from django.conf import settings

        from users.models.investor_classification import RETENTION_CLOCK

        retention_days = getattr(settings, "CLASSIFICATION_EVIDENCE_RETENTION_DAYS", 0)
        if not retention_days:
            return self.none()

        cutoff = moment - timedelta(days=retention_days)
        past_horizon = Q()
        for status, clock in RETENTION_CLOCK.items():
            past_horizon |= Q(status=status, **{f"{clock}__isnull": False, f"{clock}__lt": cutoff})

        return self.filter(past_horizon).exclude(evidence_file="").exclude(evidence_file__isnull=True)

    def for_company(self, company):
        from users.models.investor_classification import InvestorCategory

        unscoped = Q(company__isnull=True) & ~Q(category=InvestorCategory.ASSOCIATED_PERSON)
        if company is None:
            return self.filter(unscoped)
        return self.filter(unscoped | Q(company=company))
