"""
Asset Snapshot model - Historical price data
"""

from django.db import models

from assets.querysets.asset_snapshot import AssetSnapshotQuerySet
from shared.models import BaseModel

from .asset import Asset


class AssetSnapshot(BaseModel):
    """
    Historical price data for assets

    Replaces the old exchange-specific snapshot tables (ASXSnapshot, NASDAQSnapshot, etc.)
    with a single unified table.

    Extends BaseModel which provides: uuid (primary key), created_at, updated_at
    """

    # Custom manager with QuerySet methods available after chaining
    objects = AssetSnapshotQuerySet.as_manager()

    # Relationship
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="snapshots", help_text="Asset this snapshot belongs to"
    )

    # Price data
    price = models.DecimalField(max_digits=40, decimal_places=18, help_text="Price at snapshot time")
    price_currency = models.CharField(max_length=16, default="USD", help_text="Currency of price")

    # Market data (stored as JSON for flexibility)
    market_data = models.JSONField(
        default=dict, blank=True, help_text="Additional market data (volume, market cap, etc.)"
    )
    # Expected fields in market_data:
    # {
    #   "volume_24h": "decimal",
    #   "market_cap": "decimal",
    #   "change_24h": "decimal",
    #   "change_percent_24h": "decimal",
    #   "high_24h": "decimal",
    #   "low_24h": "decimal",
    #   "circulating_supply": "decimal",  # for crypto
    #   "total_supply": "decimal",  # for crypto
    #   ... (flexible based on source)
    # }

    # Source tracking
    source_timestamp = models.DateTimeField(help_text="When this data was captured")
    data_source = models.CharField(
        max_length=64, help_text="Source identifier (e.g., 'manual', 'provider_api', 'chainlink_oracle')"
    )

    # On-chain reference (if applicable)
    block_number = models.BigIntegerField(
        null=True, blank=True, help_text="Blockchain block number (if from on-chain source)"
    )
    tx_hash = models.CharField(
        max_length=128, null=True, blank=True, help_text="Transaction hash (if from on-chain source)"
    )

    # Note: created_at and updated_at are provided by BaseModel

    class Meta:
        db_table = "asset_snapshots"
        verbose_name = "Asset Snapshot"
        verbose_name_plural = "Asset Snapshots"
        indexes = [
            models.Index(fields=["asset", "-source_timestamp"], name="idx_snap_asset_time"),
            models.Index(fields=["source_timestamp"], name="idx_snap_time"),
        ]
        # Prevent duplicate snapshots for same asset + timestamp
        constraints = [models.UniqueConstraint(fields=["asset", "source_timestamp"], name="unique_asset_snapshot")]
        ordering = ["-source_timestamp"]

    def __str__(self):
        return f"{self.asset.symbol} @ {self.source_timestamp}: {self.price}"

    def __repr__(self):
        return f"<AssetSnapshot: {self.asset.symbol} {self.price} @ {self.source_timestamp}>"

    @property
    def volume_24h(self):
        """Get 24h volume from market_data"""
        return self.market_data.get("volume_24h")

    @property
    def market_cap(self):
        """Get market cap from market_data"""
        return self.market_data.get("market_cap")

    @property
    def change_24h(self):
        """Get 24h change from market_data"""
        return self.market_data.get("change_24h")

    @property
    def change_percent_24h(self):
        """Get 24h change percent from market_data"""
        return self.market_data.get("change_percent_24h")

    @property
    def high_24h(self):
        """Get 24h high from market_data"""
        return self.market_data.get("high_24h")

    @property
    def low_24h(self):
        """Get 24h low from market_data"""
        return self.market_data.get("low_24h")
