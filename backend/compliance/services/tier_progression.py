import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from compliance.constants import NEW_CUSTOMER_DAYS

if TYPE_CHECKING:
    from users.models import UserAccount

logger = logging.getLogger("ledova_backend")


class TierProgressionService:
    @classmethod
    def has_open_compliance_alerts(cls, user_account: "UserAccount") -> bool:
        from compliance.models import ComplianceAlert

        return ComplianceAlert.objects.has_open_for_user_account(user_account)

    @classmethod
    def has_active_compliance_hold(cls, user_account: "UserAccount") -> bool:
        from compliance.models import ComplianceAlert

        return ComplianceAlert.objects.has_active_hold_for_user_account(user_account)

    @classmethod
    def is_new_customer(cls, user_account: "UserAccount", days: int = NEW_CUSTOMER_DAYS) -> bool:
        if not user_account.activation_date:
            return True

        threshold = timezone.now() - timedelta(days=days)
        return user_account.activation_date > threshold
