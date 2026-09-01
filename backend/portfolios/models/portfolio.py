from decimal import Decimal
from uuid import UUID

from django.db import models

from portfolios.querysets.asset_allocation import AssetAllocationQuerySet
from portfolios.querysets.portfolio import PortfolioQuerySet
from portfolios.querysets.portfolio_snapshot import PortfolioSnapshotQuerySet
from shared.models import BaseModel
from users.models import UserAccount


class Portfolio(BaseModel):
    user_account = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=255)
    wallets = models.ManyToManyField("wallets.Wallet", related_name="portfolios", blank=True)
    is_active = models.BooleanField(default=True)

    objects = PortfolioQuerySet.as_manager()

    class Meta:
        db_table = "portfolios"
        verbose_name = "Portfolio"
        verbose_name_plural = "Portfolios"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"Portfolio for {self.user_account}"

    def account_wallets(self):
        """Return only wallet links that agree with the portfolio's tenant."""
        return self.wallets.filter(user_account_id=self.user_account_id)

    @property
    def holdings_summary(self):
        from collections import defaultdict

        aggregated = defaultdict(Decimal)
        for wallet in self.account_wallets():
            for holding in wallet.holdings.filter(asset__is_active=True):
                aggregated[holding.asset] += holding.quantity
        return dict(aggregated)


class AssetAllocation(BaseModel):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="allocations")
    asset = models.ForeignKey("assets.Asset", on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)

    objects = AssetAllocationQuerySet.as_manager()

    class Meta:
        db_table = "asset_allocations"
        unique_together = ["portfolio", "asset"]
        verbose_name = "Asset Allocation"
        verbose_name_plural = "Asset Allocations"

    def __str__(self):
        return f"{self.portfolio} - {self.asset.symbol}: {self.percentage}%"


class PortfolioSnapshot(BaseModel):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="snapshots")
    snapshot_date = models.DateField()
    snapshot_reason = models.CharField(
        max_length=50,
        choices=[
            ("DAILY", "Daily Snapshot"),
            ("MANUAL", "Manual Snapshot"),
        ],
    )
    holdings_data = models.JSONField(default=dict, blank=True)
    total_market_value = models.DecimalField(max_digits=40, decimal_places=18, null=True, blank=True)

    objects = PortfolioSnapshotQuerySet.as_manager()

    class Meta:
        db_table = "portfolio_snapshots"
        verbose_name = "Portfolio Snapshot"
        verbose_name_plural = "Portfolio Snapshots"
        indexes = [
            models.Index(fields=["portfolio", "-snapshot_date"]),
        ]

    def __str__(self):
        return f"Portfolio {self.portfolio.name} snapshot on {self.snapshot_date}"

    @property
    def has_value_data(self) -> bool:
        return self.total_market_value is not None

    def has_account_scoped_holdings(self, allowed_wallet_ids=None) -> bool:
        """Return whether embedded wallet provenance stays within the portfolio account."""
        if not isinstance(self.holdings_data, dict):
            return False

        if not self.holdings_data:
            return self.total_market_value is None or self.total_market_value == Decimal("0")

        if allowed_wallet_ids is None:
            allowed_wallet_ids = self.portfolio.user_account.wallets.values_list("uuid", flat=True)
        allowed_wallet_ids = {str(wallet_id) for wallet_id in allowed_wallet_ids}

        for holding_data in self.holdings_data.values():
            if not isinstance(holding_data, dict):
                return False

            wallet_ids = holding_data.get("wallets")
            if not isinstance(wallet_ids, list) or not wallet_ids:
                return False

            try:
                normalized_wallet_ids = {str(UUID(str(wallet_id))) for wallet_id in wallet_ids}
            except (AttributeError, TypeError, ValueError):
                return False

            if not normalized_wallet_ids.issubset(allowed_wallet_ids):
                return False

        return True

    def calculate_total_value(self):
        total = Decimal("0")
        for asset_data in self.holdings_data.values():
            if "market_value" in asset_data:
                total += Decimal(str(asset_data["market_value"]))
        return total
