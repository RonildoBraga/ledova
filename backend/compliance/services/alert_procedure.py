"""
Service for alert procedure operations.

AML/CTF Compliance:
Handles business logic for alert procedure templates, steps, and checklists.
Implements procedure management from Document 3 (Transaction Monitoring Program).
"""

import logging
from typing import TYPE_CHECKING, Dict, List

from django.utils import timezone

if TYPE_CHECKING:
    from compliance.models import AlertChecklistItem

logger = logging.getLogger("ledova_backend")


class AlertProcedureService:
    """
    Service for managing alert procedures and checklists.

    Responsibilities:
    - Creating checklists for alerts based on procedure templates
    - Tracking checklist completion statistics
    - Managing procedure step completion workflow
    """

    @classmethod
    def create_checklist_for_alert(cls, alert) -> List["AlertChecklistItem"]:
        """
        Create checklist items for an alert based on its type's procedure template.

        Args:
            alert: ComplianceAlert instance

        Returns:
            List of created AlertChecklistItem instances, or empty list if no template exists.
        """
        from compliance.models import AlertChecklistItem, AlertProcedureTemplate

        template = AlertProcedureTemplate.objects.get_for_alert(alert)

        if not template:
            logger.debug(f"[ALERT_PROCEDURE] No template found for alert type: {alert.alert_type}")
            return []

        items = []
        for step in template.steps.all().order_by("order"):
            item, created = AlertChecklistItem.objects.get_or_create(alert=alert, step=step)
            if created:
                items.append(item)
                logger.debug(f"[ALERT_PROCEDURE] Created checklist item for step {step.order}: {step.description[:50]}")

        logger.info(
            f"[ALERT_PROCEDURE] Created {len(items)} checklist items for alert {alert.uuid} "
            f"(template: {template.name})"
        )

        return items

    @classmethod
    def get_completion_stats(cls, alert) -> Dict:
        """
        Get completion statistics for an alert's checklist.

        Args:
            alert: ComplianceAlert instance

        Returns:
            Dict with completion statistics:
            - total: Total checklist items
            - completed: Completed items count
            - pending: Pending items count
            - skipped: Skipped items count
            - required_total: Required items count
            - required_completed: Completed required items count
            - completion_percentage: Overall completion percentage
            - required_completion_percentage: Required items completion percentage
        """
        from compliance.models import AlertChecklistItem

        items = AlertChecklistItem.objects.filter(alert=alert)
        total = items.count()

        if total == 0:
            return {
                "total": 0,
                "completed": 0,
                "pending": 0,
                "skipped": 0,
                "required_total": 0,
                "required_completed": 0,
                "completion_percentage": 0,
                "required_completion_percentage": 0,
            }

        completed = items.filter(is_completed=True).count()
        pending = items.filter(is_completed=False, is_skipped=False).count()
        skipped = items.filter(is_skipped=True).count()
        required_items = items.filter(step__is_required=True)
        required_total = required_items.count()
        required_completed = required_items.filter(is_completed=True).count()

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "skipped": skipped,
            "required_total": required_total,
            "required_completed": required_completed,
            "completion_percentage": round((completed / total) * 100) if total > 0 else 0,
            "required_completion_percentage": (
                round((required_completed / required_total) * 100) if required_total > 0 else 0
            ),
        }

    @classmethod
    def mark_step_completed(cls, checklist_item, user, notes: str = "") -> None:
        """
        Mark a checklist item as completed.

        Args:
            checklist_item: AlertChecklistItem instance
            user: User who completed the step
            notes: Optional notes about the completion
        """
        checklist_item.is_completed = True
        checklist_item.completed_at = timezone.now()
        checklist_item.completed_by = user
        if notes:
            checklist_item.notes = notes
        checklist_item.save()

        logger.info(
            f"[ALERT_PROCEDURE] Step {checklist_item.step.order} completed by {user} "
            f"for alert {checklist_item.alert.uuid}"
        )

    @classmethod
    def mark_step_skipped(cls, checklist_item, reason: str) -> None:
        """
        Mark a checklist item as skipped.

        Args:
            checklist_item: AlertChecklistItem instance
            reason: Reason for skipping the step
        """
        checklist_item.is_skipped = True
        checklist_item.skip_reason = reason
        checklist_item.save()

        logger.info(
            f"[ALERT_PROCEDURE] Step {checklist_item.step.order} skipped "
            f"for alert {checklist_item.alert.uuid}: {reason}"
        )

    @classmethod
    def get_overdue_items(cls, alert) -> List["AlertChecklistItem"]:
        """
        Get all overdue checklist items for an alert.

        Args:
            alert: ComplianceAlert instance

        Returns:
            List of AlertChecklistItem instances that are overdue.
        """
        from compliance.models import AlertChecklistItem, AlertProcedureTemplate

        template = AlertProcedureTemplate.objects.get_for_alert(alert)
        if not template:
            return []

        deadline = alert.created_at + timezone.timedelta(hours=template.response_time_hours)
        if timezone.now() <= deadline:
            return []

        # Return required pending items as overdue
        return list(AlertChecklistItem.objects.pending_required_for_alert(alert))
