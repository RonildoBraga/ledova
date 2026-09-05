from django.db import models

from compliance.constants import (
    ALERT_SEVERITY_CHOICES,
    ALERT_SEVERITY_MEDIUM,
    RULE_TYPE_CHOICES,
)
from compliance.querysets.monitoring_rule import MonitoringRuleQuerySet
from shared.models.base import BaseModel


class MonitoringRule(BaseModel):

    rule_code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Unique rule code, e.g., MON-001",
    )
    name = models.CharField(max_length=100)
    description = models.TextField()
    rule_type = models.CharField(
        max_length=30,
        choices=RULE_TYPE_CHOICES,
        help_text="Type of check: threshold, velocity, pattern, address, etc.",
    )

    parameters = models.JSONField(
        default=dict,
        help_text="Rule-specific parameters (thresholds, timeframes, etc.)",
    )
    alert_severity = models.CharField(
        max_length=20,
        choices=ALERT_SEVERITY_CHOICES,
        default=ALERT_SEVERITY_MEDIUM,
    )
    is_active = models.BooleanField(default=True)

    objects = MonitoringRuleQuerySet.as_manager()

    class Meta:
        ordering = ["rule_code"]
        verbose_name = "Monitoring Rule"
        verbose_name_plural = "⚙️ Setup: Monitoring Rules"

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.rule_code}: {self.name} ({status})"
