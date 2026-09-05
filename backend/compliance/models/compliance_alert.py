from django.db import models

from compliance.constants import (
    ACCOUNT_ACTION_CHOICES,
    ALERT_SEVERITY_CHOICES,
    ALERT_STATUS_CHOICES,
    ALERT_STATUS_NEW,
    ALERT_TYPE_CHOICES,
    INVESTIGATION_OUTCOME_CHOICES,
    SMR_TYPE_CHOICES,
)
from shared.models.base import BaseModel


class ComplianceAlert(BaseModel):
    """Alert raised by a monitoring rule, a crypto screening, the periodic-review task or an officer by hand."""

    user_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.CASCADE,
        related_name="compliance_alerts",
    )
    transaction = models.ForeignKey(
        "wallets.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compliance_alerts",
        help_text="Crypto transaction that triggered the alert",
    )
    monitoring_rule = models.ForeignKey(
        "compliance.MonitoringRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_alerts",
        help_text="Rule that triggered this alert (null for manual alerts)",
    )
    alert_type = models.CharField(
        max_length=50,
        choices=ALERT_TYPE_CHOICES,
    )
    severity = models.CharField(
        max_length=20,
        choices=ALERT_SEVERITY_CHOICES,
    )
    triggered_rule = models.CharField(
        max_length=20,
        help_text="Rule code that triggered this alert",
    )
    description = models.TextField()
    alert_data = models.JSONField(
        default=dict,
        help_text="Additional data about the alert (thresholds, values, etc.)",
    )
    status = models.CharField(
        max_length=20,
        choices=ALERT_STATUS_CHOICES,
        default=ALERT_STATUS_NEW,
    )
    assigned_to = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_alerts",
    )
    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    resolution_notes = models.TextField(
        blank=True,
        help_text="Notes on how the alert was resolved",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    resolved_by = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )
    investigation_outcome = models.CharField(
        max_length=30,
        choices=INVESTIGATION_OUTCOME_CHOICES,
        null=True,
        blank=True,
        help_text="Final outcome of the investigation",
    )
    smr_required = models.BooleanField(
        default=False,
        help_text="Whether an SMR needs to be filed",
    )
    smr_type = models.CharField(
        max_length=20,
        choices=SMR_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text="Type of SMR: TF (24hr deadline) or ML (3 business days)",
    )
    smr_reference = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="AUSTRAC SMR reference number (for quick lookup)",
    )
    smr_filed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the SMR was filed with AUSTRAC",
    )
    account_action = models.CharField(
        max_length=30,
        choices=ACCOUNT_ACTION_CHOICES,
        null=True,
        blank=True,
        help_text="Action taken on the customer account",
    )
    account_action_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the account action was applied",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["user_account", "-created_at"]),
            models.Index(fields=["severity", "status"]),
            models.Index(fields=["triggered_rule"]),
            models.Index(fields=["smr_required", "smr_filed_at"]),
            models.Index(fields=["account_action"]),
        ]

    def __str__(self):
        return f"{self.triggered_rule} - {self.alert_type} ({self.status})"
