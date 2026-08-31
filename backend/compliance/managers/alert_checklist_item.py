"""
Manager for AlertChecklistItem model.
"""

from django.db import models

from compliance.querysets.alert_checklist_item import AlertChecklistItemQuerySet


class AlertChecklistItemManager(models.Manager.from_queryset(AlertChecklistItemQuerySet)):
    """Manager for AlertChecklistItem with custom convenience methods."""

    def pending_required_for_alert(self, alert):
        """
        Get pending required checklist items for an alert, ordered by step.

        Args:
            alert: ComplianceAlert instance

        Returns:
            QuerySet of AlertChecklistItem instances.
        """
        return self.filter(alert=alert).required_pending().order_by("step__order")

    def is_complete_for_alert(self, alert) -> bool:
        """
        Check if all required steps for an alert are complete.

        Args:
            alert: ComplianceAlert instance

        Returns:
            True if all required steps are completed or skipped, False otherwise.
        """
        return not self.filter(alert=alert).required_pending().exists()
