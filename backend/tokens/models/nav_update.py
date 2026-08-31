from django.conf import settings
from django.db import models

from shared.models import BaseModel


class NAVUpdate(BaseModel):
    yield_token = models.ForeignKey(
        "tokens.YieldToken",
        on_delete=models.PROTECT,
        related_name="nav_updates",
        help_text="The yield token whose NAV was updated",
    )

    old_nav_per_token = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        help_text="Previous NAV per token",
    )

    new_nav_per_token = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        help_text="New NAV per token",
    )

    total_reserve_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        help_text="Synthetic reference value at time of update",
    )

    custodian_report_ref = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional synthetic scenario reference (legacy field name)",
    )

    transaction = models.ForeignKey(
        "blockchain.BlockchainTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nav_updates",
        help_text="On-chain transaction for this NAV update (if executed on-chain)",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="nav_updates",
        help_text="Staff member who performed this update",
    )

    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this NAV update",
    )

    class Meta:
        verbose_name = "NAV Update"
        verbose_name_plural = "NAV Updates"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.yield_token.symbol} NAV: " f"${self.old_nav_per_token} → ${self.new_nav_per_token}"
