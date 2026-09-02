from django.db.models import QuerySet

from compliance.constants import (
    ACCOUNT_ACTION_SUSPENDED,
    ACCOUNT_ACTION_TRANSACTION_HOLD,
    ALERT_STATUS_CLOSED,
    ALERT_STATUS_NEW,
)


class ComplianceAlertQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def new(self):
        return self.filter(status=ALERT_STATUS_NEW)

    def open(self):
        return self.exclude(status=ALERT_STATUS_CLOSED)

    def for_user_account(self, user_account):
        return self.filter(user_account=user_account)

    def with_active_hold(self):
        return self.filter(account_action__in=[ACCOUNT_ACTION_TRANSACTION_HOLD, ACCOUNT_ACTION_SUSPENDED])

    def has_open_for_user_account(self, user_account) -> bool:
        return self.for_user_account(user_account).open().exists()

    def has_active_hold_for_user_account(self, user_account) -> bool:
        return self.for_user_account(user_account).with_active_hold().exists()
