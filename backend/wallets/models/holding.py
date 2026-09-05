from django.db import models

from shared.models import BaseModel
from wallets.querysets.holding import HoldingQuerySet


class Holding(BaseModel):

    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.CASCADE, related_name="holdings")
    asset = models.ForeignKey("assets.Asset", on_delete=models.CASCADE, related_name="holdings")
    quantity = models.DecimalField(max_digits=40, decimal_places=18)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    objects = HoldingQuerySet.as_manager()

    class Meta:
        db_table = "holdings"
        verbose_name = "Holding"
        verbose_name_plural = "Holdings"
        constraints = [models.UniqueConstraint(fields=["wallet", "asset"], name="unique_wallet_asset")]
        indexes = [
            models.Index(fields=["wallet"], name="idx_holding_wallet"),
            models.Index(fields=["asset"], name="idx_holding_asset"),
        ]
        ordering = ["-quantity"]

    def __str__(self):
        return f"{self.wallet.address[:10]}... - {self.asset.symbol}: {self.quantity}"

    def __repr__(self):
        return f"<Holding: {self.wallet.address[:10]}... {self.asset.symbol} {self.quantity}>"

    @property
    def market_value(self):
        if self.asset.current_price:
            return self.quantity * self.asset.current_price
        return None
