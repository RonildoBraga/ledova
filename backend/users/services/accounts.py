from compliance.services.risk_assessment import RiskAssessmentService
from shared.db import atomic
from users.constants import USER_ACCOUNT_TYPE_INDIVIDUAL
from users.models import NotificationPreferences


@atomic()
def register_account(account, profile):
    account.user_profiles.add(profile)
    if account.account_type == USER_ACCOUNT_TYPE_INDIVIDUAL:
        account.director = profile
        account.save(update_fields=["director"])
    RiskAssessmentService.create_pending_assessment(user_account=account)
    return account


def ensure_notification_preferences(user_profile):
    preferences, _ = NotificationPreferences.objects.get_or_create(user_profile=user_profile)
    return preferences
