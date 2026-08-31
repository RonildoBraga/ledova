"""
AlertProcedureStep model for defining steps within procedure templates.

AML/CTF Compliance:
Defines the individual steps that must be completed when investigating
an alert, derived from the policy documents.

This standalone source release does not include an external policy document.
"""

from django.db import models

from compliance.querysets.alert_procedure_step import AlertProcedureStepQuerySet
from shared.models.base import BaseModel


class AlertProcedureStep(BaseModel):
    """
    Individual step within an alert procedure template.

    AML/CTF Compliance: Each step represents an action the Compliance Officer
    must take when investigating an alert of the associated type.
    """

    template = models.ForeignKey(
        "compliance.AlertProcedureTemplate",
        on_delete=models.CASCADE,
        related_name="steps",
        help_text="The procedure template this step belongs to",
    )

    # Step ordering
    order = models.PositiveIntegerField(
        help_text="Order of this step in the procedure (1-based)",
    )

    # Step content
    description = models.CharField(
        max_length=255,
        help_text="Brief description of the action to take",
    )
    detailed_instructions = models.TextField(
        blank=True,
        help_text="Detailed instructions for completing this step",
    )

    # Requirements
    is_required = models.BooleanField(
        default=True,
        help_text="Whether this step must be completed",
    )

    # Conditional logic
    condition = models.CharField(
        max_length=255,
        blank=True,
        help_text="Condition under which this step applies (e.g., 'If SMR required')",
    )

    # Help text and references
    help_text = models.TextField(
        blank=True,
        help_text="Additional guidance for completing this step",
    )
    policy_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific policy reference for this step",
    )

    objects = AlertProcedureStepQuerySet.as_manager()

    class Meta:
        ordering = ["template", "order"]
        unique_together = [["template", "order"]]
        verbose_name = "Procedure Step"
        verbose_name_plural = "⚙️ Setup: Procedure Steps"
        indexes = [
            models.Index(fields=["template", "order"]),
            models.Index(fields=["is_required"]),
        ]

    def __str__(self):
        return f"Step {self.order}: {self.description[:50]}"

    @property
    def is_conditional(self):
        """Check if this step has a condition."""
        return bool(self.condition)
