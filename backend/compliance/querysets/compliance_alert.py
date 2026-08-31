from django.db.models import QuerySet
from django.utils import timezone

from compliance.constants import (
    ACCOUNT_ACTION_SUSPENDED,
    ACCOUNT_ACTION_TRANSACTION_HOLD,
    ALERT_SEVERITY_CRITICAL,
    ALERT_SEVERITY_HIGH,
    ALERT_STATUS_CLOSED,
    ALERT_STATUS_ESCALATED,
    ALERT_STATUS_NEW,
    ALERT_STATUS_REVIEWING,
)


class ComplianceAlertQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def new(self):
        return self.filter(status=ALERT_STATUS_NEW)

    def reviewing(self):
        return self.filter(status=ALERT_STATUS_REVIEWING)

    def escalated(self):
        return self.filter(status=ALERT_STATUS_ESCALATED)

    def closed(self):
        return self.filter(status=ALERT_STATUS_CLOSED)

    def open(self):
        return self.exclude(status=ALERT_STATUS_CLOSED)

    def critical(self):
        return self.filter(severity=ALERT_SEVERITY_CRITICAL)

    def high_priority(self):
        return self.filter(severity__in=[ALERT_SEVERITY_CRITICAL, ALERT_SEVERITY_HIGH])

    def for_user_account(self, user_account):
        return self.filter(user_account=user_account)

    def assigned_to(self, user):
        return self.filter(assigned_to=user)

    def unassigned(self):
        return self.filter(assigned_to__isnull=True)

    def by_rule(self, rule_code):
        return self.filter(triggered_rule=rule_code)

    def recent(self, hours=24):
        since = timezone.now() - timezone.timedelta(hours=hours)
        return self.filter(created_at__gte=since)

    def pending_investigation(self):
        return self.filter(investigation_outcome__isnull=True).exclude(status=ALERT_STATUS_CLOSED)

    def with_active_hold(self):
        return self.filter(account_action__in=[ACCOUNT_ACTION_TRANSACTION_HOLD, ACCOUNT_ACTION_SUSPENDED])
