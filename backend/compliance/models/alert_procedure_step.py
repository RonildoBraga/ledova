from django.db import models

from shared.models.base import BaseModel


class AlertProcedureStep(BaseModel):
    template = models.ForeignKey(
        "compliance.AlertProcedureTemplate",
        on_delete=models.CASCADE,
        related_name="steps",
        help_text="The procedure template this step belongs to",
    )
    order = models.PositiveIntegerField(
        help_text="Order of this step in the procedure (1-based)",
    )
    description = models.CharField(
        max_length=255,
        help_text="Brief description of the action to take",
    )
    detailed_instructions = models.TextField(
        blank=True,
        help_text="Detailed instructions for completing this step",
    )
    is_required = models.BooleanField(
        default=True,
        help_text="Whether this step must be completed",
    )
    condition = models.CharField(
        max_length=255,
        blank=True,
        help_text="Condition under which this step applies (e.g., 'If SMR required')",
    )
    help_text = models.TextField(
        blank=True,
        help_text="Additional guidance for completing this step",
    )
    policy_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific policy reference for this step",
    )

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
        return bool(self.condition)
