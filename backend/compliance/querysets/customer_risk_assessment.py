from django.db.models import QuerySet
from django.utils import timezone

from compliance.constants import (
    ASSESSMENT_STATUS_COMPLETE,
    ASSESSMENT_STATUS_INCOMPLETE,
    ASSESSMENT_STATUS_PENDING,
    RISK_RATING_EXTREME,
    RISK_RATING_HIGH,
)


class CustomerRiskAssessmentQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def complete(self):
        return self.filter(assessment_status=ASSESSMENT_STATUS_COMPLETE)

    def pending(self):
        return self.filter(assessment_status=ASSESSMENT_STATUS_PENDING)

    def incomplete(self):
        return self.filter(assessment_status=ASSESSMENT_STATUS_INCOMPLETE)

    def high_risk(self):
        return self.filter(overall_risk_rating__in=[RISK_RATING_HIGH, RISK_RATING_EXTREME])

    def due_for_review(self):
        return self.filter(
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            next_review_date__lte=timezone.now(),
        )

    def for_user_account(self, user_account):
        return self.filter(user_account=user_account)

    def latest_for_user(self, user_account):
        return self.filter(user_account=user_account).order_by("-created_at").first()

    def valid(self):
        now = timezone.now()
        return self.filter(
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            valid_from__lte=now,
            valid_until__gt=now,
        )
