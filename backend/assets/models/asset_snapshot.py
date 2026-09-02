from django.db import models

from assets.querysets.asset_snapshot import AssetSnapshotQuerySet
from shared.models import BaseModel

from .asset import Asset


class AssetSnapshot(BaseModel):
    objects = AssetSnapshotQuerySet.as_manager()

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="snapshots", help_text="Asset this snapshot belongs to"
    )

    price = models.DecimalField(max_digits=40, decimal_places=18, help_text="Price at snapshot time")
    price_currency = models.CharField(max_length=16, default="USD", help_text="Currency of price")

    market_data = models.JSONField(
        default=dict, blank=True, help_text="Additional market data (volume, market cap, etc.)"
    )

    source_timestamp = models.DateTimeField(help_text="When this data was captured")
    data_source = models.CharField(
        max_length=64, help_text="Source identifier (e.g., 'manual', 'provider_api', 'chainlink_oracle')"
    )

    block_number = models.BigIntegerField(
        null=True, blank=True, help_text="Blockchain block number (if from on-chain source)"
    )
    tx_hash = models.CharField(
        max_length=128, null=True, blank=True, help_text="Transaction hash (if from on-chain source)"
    )

    class Meta:
        db_table = "asset_snapshots"
        verbose_name = "Asset Snapshot"
        verbose_name_plural = "Asset Snapshots"
        indexes = [
            models.Index(fields=["asset", "-source_timestamp"], name="idx_snap_asset_time"),
            models.Index(fields=["source_timestamp"], name="idx_snap_time"),
        ]
        constraints = [models.UniqueConstraint(fields=["asset", "source_timestamp"], name="unique_asset_snapshot")]
        ordering = ["-source_timestamp"]

    def __str__(self):
        return f"{self.asset.symbol} @ {self.source_timestamp}: {self.price}"

    def __repr__(self):
        return f"<AssetSnapshot: {self.asset.symbol} {self.price} @ {self.source_timestamp}>"
