from django.db import models

from shared.models import BaseModel


class Stablecoin(BaseModel):
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10, unique=True)
    contract_address = models.CharField(max_length=42, unique=True)
    decimals = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    reserve_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    reserve_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Stablecoin"
        verbose_name_plural = "Stablecoins"
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"
