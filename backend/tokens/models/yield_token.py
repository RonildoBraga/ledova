from django.db import models

from shared.models import BaseModel


class YieldToken(BaseModel):
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10, unique=True)
    contract_address = models.CharField(max_length=42, unique=True)
    decimals = models.PositiveSmallIntegerField(default=6)
    is_active = models.BooleanField(default=True)

    nav_per_token = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Current NAV per token in USD (e.g., 1.005000)",
    )

    total_reserve_value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Synthetic reference value in USD; not evidence of a real reserve",
    )

    last_nav_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last NAV update",
    )

    class Meta:
        verbose_name = "Yield Token"
        verbose_name_plural = "Yield Tokens"
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"
