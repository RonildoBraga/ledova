from django.db.models import Q, QuerySet
from django.utils import timezone


class InvestorClassificationQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_account__user_profiles__user=user)

    def manageable_by_user(self, user):
        from users.models.investor_classification import InvestorClassificationStatus

        return self.visible_to_user(user).filter(status=InvestorClassificationStatus.SUBMITTED)

    def live(self):
        from users.models.investor_classification import InvestorClassificationStatus

        return self.filter(status=InvestorClassificationStatus.VERIFIED).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )

    def for_company(self, company):
        from users.models.investor_classification import InvestorCategory

        unscoped = Q(company__isnull=True) & ~Q(category=InvestorCategory.ASSOCIATED_PERSON)
        if company is None:
            return self.filter(unscoped)
        return self.filter(unscoped | Q(company=company))
