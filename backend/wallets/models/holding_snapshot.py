from django.db import models

from shared.models import BaseModel
from wallets.constants import SNAPSHOT_REASON_CHOICES


class HoldingSnapshot(BaseModel):

    holding = models.ForeignKey(
        "wallets.Holding",
        on_delete=models.CASCADE,
        related_name="snapshots",
    )

    quantity = models.DecimalField(max_digits=40, decimal_places=18)
    block_number = models.BigIntegerField(null=True, blank=True)
    snapshot_date = models.DateField(db_index=True)
    snapshot_reason = models.CharField(max_length=32, db_index=True, choices=SNAPSHOT_REASON_CHOICES)
    caused_by_transaction = models.ForeignKey(
        "wallets.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="holding_snapshots",
    )

    class Meta:
        db_table = "holding_snapshots"
        verbose_name = "Holding Snapshot"
        verbose_name_plural = "Holding Snapshots"
        ordering = ["-snapshot_date"]
        unique_together = [["holding", "snapshot_date"]]
        indexes = [
            models.Index(fields=["holding", "-snapshot_date"], name="idx_hsnap_hold_date"),
            models.Index(fields=["snapshot_date"], name="idx_hsnap_date"),
            models.Index(fields=["snapshot_reason"], name="idx_hsnap_reason"),
            models.Index(fields=["holding", "snapshot_reason"], name="idx_hsnap_hold_reason"),
        ]

    def __str__(self):
        return (
            f"{self.holding.wallet.address[:10]}... - {self.holding.asset.symbol}: "
            f"{self.quantity} on {self.snapshot_date}"
        )

    def __repr__(self):
        return (
            f"<HoldingSnapshot: {self.holding.asset.symbol} {self.quantity} "
            f"({self.snapshot_reason}) @ {self.snapshot_date}>"
        )

    @property
    def wallet(self):
        return self.holding.wallet

    @property
    def asset(self):
        return self.holding.asset

    @property
    def market_value(self):
        from assets.models import AssetSnapshot

        snapshot = (
            AssetSnapshot.objects.filter(asset=self.holding.asset, source_timestamp__date=self.snapshot_date)
            .order_by("-source_timestamp")
            .first()
        )
        if snapshot:
            return self.quantity * snapshot.price
        return None
