from django.db import models
from django.utils import timezone

from shared.models.base import BaseModel


class AlertChecklistItem(BaseModel):

    alert = models.ForeignKey(
        "compliance.ComplianceAlert",
        on_delete=models.CASCADE,
        related_name="checklist_items",
        help_text="The alert this checklist item belongs to",
    )
    step = models.ForeignKey(
        "compliance.AlertProcedureStep",
        on_delete=models.CASCADE,
        related_name="checklist_items",
        help_text="The procedure step this tracks",
    )
    is_completed = models.BooleanField(
        default=False,
        help_text="Whether this step has been completed",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this step was completed",
    )
    completed_by = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_checklist_items",
        help_text="User who completed this step",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes or findings from completing this step",
    )
    is_skipped = models.BooleanField(
        default=False,
        help_text="Whether this step was intentionally skipped",
    )
    skip_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reason for skipping this step (if skipped)",
    )
    evidence_references = models.JSONField(
        default=list,
        blank=True,
        help_text="References to evidence or documents related to this step",
    )

    class Meta:
        ordering = ["alert", "step__order"]
        unique_together = [["alert", "step"]]
        verbose_name = "Checklist Item"
        verbose_name_plural = "Checklist Items"
        indexes = [
            models.Index(fields=["alert", "is_completed"]),
            models.Index(fields=["completed_by", "-completed_at"]),
            models.Index(fields=["is_completed", "is_skipped"]),
        ]

    def __str__(self):
        status = "Completed" if self.is_completed else ("Skipped" if self.is_skipped else "Pending")
        return f"{self.step.description[:30]} - {status}"

    def mark_completed(self, user, notes=""):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.completed_by = user
        if notes:
            self.notes = notes
        self.save()

    @property
    def is_overdue(self):
        if self.is_completed or self.is_skipped or not self.step.is_required:
            return False
        deadline = self.alert.created_at + timezone.timedelta(hours=self.step.template.response_time_hours)
        return timezone.now() > deadline
