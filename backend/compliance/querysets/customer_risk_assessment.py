from django.db.models import QuerySet
from django.utils import timezone

from compliance.constants import ASSESSMENT_STATUS_COMPLETE, ASSESSMENT_STATUS_PENDING


class CustomerRiskAssessmentQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def pending(self):
        return self.filter(assessment_status=ASSESSMENT_STATUS_PENDING)

    def due_for_review(self):
        return self.filter(
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            next_review_date__lte=timezone.now(),
        )

    def for_user_account(self, user_account):
        return self.filter(user_account=user_account)
