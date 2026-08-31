from django.db.models import QuerySet

from compliance.constants import (
    PROCEDURE_PRIORITY_CRITICAL,
    PROCEDURE_PRIORITY_HIGH,
    PROCEDURE_PRIORITY_LOW,
    PROCEDURE_PRIORITY_MEDIUM,
    SMR_REQUIREMENT_MANDATORY,
)


class AlertProcedureTemplateQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user and (user.is_superuser or user.is_staff):
            return self
        return self.none()

    def active(self):
        return self.filter(is_active=True)

    def critical(self):
        return self.filter(priority=PROCEDURE_PRIORITY_CRITICAL)

    def high_priority(self):
        return self.filter(priority__in=[PROCEDURE_PRIORITY_CRITICAL, PROCEDURE_PRIORITY_HIGH])

    def medium_priority(self):
        return self.filter(priority=PROCEDURE_PRIORITY_MEDIUM)

    def low_priority(self):
        return self.filter(priority=PROCEDURE_PRIORITY_LOW)

    def smr_mandatory(self):
        return self.filter(smr_requirement=SMR_REQUIREMENT_MANDATORY)

    def escalation_required(self):
        return self.filter(escalation_required=True)

    def no_customer_notification(self):
        return self.filter(customer_notification_allowed=False)
