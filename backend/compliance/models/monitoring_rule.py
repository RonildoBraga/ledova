"""
MonitoringRule model for configurable transaction monitoring rules.

AML/CTF Compliance:
Implements monitoring scenarios from Document 3 (Transaction Monitoring Program) Section 3.
Rules are stored in database to allow configuration without code changes.
"""

from django.db import models

from compliance.constants import (
    ALERT_SEVERITY_CHOICES,
    ALERT_SEVERITY_MEDIUM,
    RULE_TYPE_CHOICES,
)
from compliance.querysets.monitoring_rule import MonitoringRuleQuerySet
from shared.models.base import BaseModel


class MonitoringRule(BaseModel):
    """
    Configurable transaction monitoring rule.

    AML/CTF Compliance: Implements monitoring scenarios from Document 3
    (Transaction Monitoring Program) Section 3.

    Rules are stored in database to allow configuration without code changes.
    """

    # Rule identification
    rule_code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Unique rule code, e.g., MON-001",
    )
    name = models.CharField(max_length=100)
    description = models.TextField()

    # Rule type
    rule_type = models.CharField(
        max_length=30,
        choices=RULE_TYPE_CHOICES,
        help_text="Type of check: threshold, velocity, pattern, address, etc.",
    )

    # Rule parameters (flexible JSON for different rule types)
    parameters = models.JSONField(
        default=dict,
        help_text="Rule-specific parameters (thresholds, timeframes, etc.)",
    )
    # Example parameters:
    # Threshold: {"amount": 10000, "currency": "AUD"}
    # Velocity: {"max_amount": 25000, "period_hours": 24}
    # Pattern: {"min_transactions": 3, "max_each": 9500, "period_hours": 48}

    # Alert configuration
    alert_severity = models.CharField(
        max_length=20,
        choices=ALERT_SEVERITY_CHOICES,
        default=ALERT_SEVERITY_MEDIUM,
    )

    # Rule status
    is_active = models.BooleanField(default=True)

    objects = MonitoringRuleQuerySet.as_manager()

    class Meta:
        ordering = ["rule_code"]
        verbose_name = "Monitoring Rule"
        verbose_name_plural = "⚙️ Setup: Monitoring Rules"

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.rule_code}: {self.name} ({status})"
