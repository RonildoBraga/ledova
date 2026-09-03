from django.db import models

from shared.models.base import BaseModel


class ExchangeRate(BaseModel):
    base_currency = models.CharField(max_length=8, default="USD")
    target_currency = models.CharField(max_length=8)
    rate = models.DecimalField(max_digits=20, decimal_places=10)

    class Meta:
        unique_together = ("base_currency", "target_currency")
        indexes = [
            models.Index(fields=["base_currency", "target_currency"], name="idx_exchange_rate_pair"),
        ]

    def __str__(self):
        return f"{self.base_currency}/{self.target_currency}: {self.rate}"
