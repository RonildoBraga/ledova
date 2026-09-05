from django.db import models

from compliance.constants import (
    ALERT_TYPE_CHOICES,
    ESCALATION_TIMEFRAME_CHOICES,
    ESCALATION_TIMEFRAME_IF_CONCERNS,
    PROCEDURE_PRIORITY_CHOICES,
    PROCEDURE_PRIORITY_MEDIUM,
    SMR_REQUIREMENT_ASSESS,
    SMR_REQUIREMENT_CHOICES,
)
from shared.models.base import BaseModel


class AlertProcedureTemplate(BaseModel):

    alert_type = models.CharField(
        max_length=50,
        choices=ALERT_TYPE_CHOICES,
        unique=True,
        help_text="The alert type this template applies to",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable name for the procedure",
    )
    description = models.TextField(
        help_text="Description of when this procedure applies",
    )
    priority = models.CharField(
        max_length=20,
        choices=PROCEDURE_PRIORITY_CHOICES,
        default=PROCEDURE_PRIORITY_MEDIUM,
        help_text="Priority level determining response timeframe",
    )
    response_time_hours = models.PositiveIntegerField(
        help_text="Maximum response time in hours",
    )
    policy_references = models.JSONField(
        default=list,
        help_text="List of policy document references (e.g., ['Doc 3 §7', 'Doc 5 §12'])",
    )
    smr_requirement = models.CharField(
        max_length=20,
        choices=SMR_REQUIREMENT_CHOICES,
        default=SMR_REQUIREMENT_ASSESS,
        help_text="Whether SMR is required for this alert type",
    )
    smr_timeframe_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="SMR deadline in hours (24 for TF, 72 for ML)",
    )
    escalation_required = models.BooleanField(
        default=False,
        help_text="Whether escalation to Director is required",
    )
    escalation_timeframe = models.CharField(
        max_length=30,
        choices=ESCALATION_TIMEFRAME_CHOICES,
        default=ESCALATION_TIMEFRAME_IF_CONCERNS,
        help_text="When escalation should occur",
    )
    customer_notification_allowed = models.BooleanField(
        default=True,
        help_text="Whether customer can be notified (false for tipping-off risk)",
    )
    required_documentation = models.JSONField(
        default=list,
        help_text="List of required documentation items for this alert type",
    )
    outcome_options = models.JSONField(
        default=list,
        help_text="List of possible outcomes with their actions",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this template is currently in use",
    )

    class Meta:
        ordering = ["priority", "alert_type"]
        verbose_name = "Procedure Template"
        verbose_name_plural = "⚙️ Setup: Procedure Templates"

    def __str__(self):
        return f"{self.name} ({self.get_priority_display()})"

    @property
    def step_count(self):
        return self.steps.count()

    @property
    def required_step_count(self):
        return self.steps.filter(is_required=True).count()
