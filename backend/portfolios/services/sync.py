import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from assets.models import AssetSnapshot
from portfolios.models import Portfolio, PortfolioSnapshot
from shared.utils.logging_utils import LoggingContext
from wallets.constants import SNAPSHOT_REASON_DAILY
from wallets.models import Holding, HoldingSnapshot, Transaction

logger = logging.getLogger("ledova_backend")


class PortfolioSyncService:

    @staticmethod
    def sync_portfolio(
        portfolio: Portfolio,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, Any]:
        logger.info(f"{LoggingContext.PORTFOLIOS} Syncing portfolio {portfolio.name}")

        try:
            wallets = portfolio.account_wallets()
            if not wallets.exists():
                return {"status": "success", "snapshots_created": 0}

            PortfolioSyncService._ensure_holding_snapshots(wallets)

            start_date, end_date = PortfolioSyncService._determine_date_range(wallets, start_date, end_date)
            logger.info(f"{LoggingContext.PORTFOLIOS} Date range: {start_date.date()} to {end_date.date()}")

            snapshots_created = 0
            current_date = start_date.date()
            end_date_only = end_date.date()

            with transaction.atomic():
                while current_date <= end_date_only:
                    snapshot_datetime = timezone.make_aware(
                        datetime.combine(current_date, settings.PORTFOLIO_SNAPSHOT_TIME_UTC)
                    )
                    if PortfolioSyncService._create_snapshot_for_date(portfolio, wallets, snapshot_datetime):
                        snapshots_created += 1
                    current_date += timedelta(days=1)

            logger.info(
                f"{LoggingContext.PORTFOLIOS} Sync completed for {portfolio.name} "
                f"- Created {snapshots_created} snapshots"
            )
            return {"status": "success", "snapshots_created": snapshots_created}

        except Exception as e:
            logger.error(f"{LoggingContext.PORTFOLIOS} Failed to sync {portfolio.name}: {e}")
            return {"status": "error", "error": str(e), "snapshots_created": 0}

    @staticmethod
    def _ensure_holding_snapshots(wallets) -> int:
        existing_count = HoldingSnapshot.objects.filter_by_wallets(wallets).count()
        if existing_count > 0:
            return 0

        today = timezone.now().date()
        holdings = Holding.objects.filter_by_wallets(wallets).active_assets_only().with_optimized_data()

        created = 0
        for holding in holdings:
            first_tx = (
                Transaction.objects.filter(wallet=holding.wallet, asset=holding.asset)
                .order_by("block_timestamp")
                .first()
            )
            if first_tx:
                holding_start = first_tx.block_timestamp.date()
            else:
                holding_start = holding.created_at.date()

            current_date = holding_start
            while current_date <= today:
                HoldingSnapshot.objects.get_or_create(
                    holding=holding,
                    snapshot_date=current_date,
                    defaults={"quantity": holding.quantity or Decimal("0"), "snapshot_reason": SNAPSHOT_REASON_DAILY},
                )
                created += 1
                current_date += timedelta(days=1)

        if created > 0:
            logger.info(f"{LoggingContext.PORTFOLIOS} Created {created} holding snapshots for backfill")
        return created

    @staticmethod
    def _determine_date_range(
        wallets, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> tuple[datetime, datetime]:
        earliest_snapshot = HoldingSnapshot.objects.filter_by_wallets(wallets).order_by("snapshot_date").first()

        if earliest_snapshot:
            earliest_date = timezone.make_aware(
                datetime.combine(earliest_snapshot.snapshot_date, settings.PORTFOLIO_SNAPSHOT_TIME_UTC)
            )
        else:
            earliest_date = timezone.now()

        if start_date is None:
            start_date = earliest_date
        else:
            start_date = max(start_date, earliest_date)

        if end_date is None:
            end_date = timezone.now()

        return start_date, end_date

    @staticmethod
    def _create_snapshot_for_date(portfolio: Portfolio, wallets, snapshot_date: datetime) -> bool:
        snapshot_date_only = snapshot_date.date()

        existing = PortfolioSnapshot.objects.filter_by_portfolio(portfolio).for_date(snapshot_date_only).first()
        if existing and existing.total_market_value is not None:
            return False

        holdings_data, total_value = PortfolioSyncService._aggregate_holdings(wallets, snapshot_date)

        if existing:
            if total_value > 0:
                existing.holdings_data = holdings_data
                existing.total_market_value = total_value
                existing.save(update_fields=["holdings_data", "total_market_value", "updated_at"])
                return True
            return False

        PortfolioSnapshot.objects.create(
            portfolio=portfolio,
            snapshot_date=snapshot_date_only,
            snapshot_reason="DAILY",
            holdings_data=holdings_data,
            total_market_value=total_value if total_value > 0 else None,
        )
        logger.info(f"{LoggingContext.PORTFOLIOS} Created snapshot for {portfolio.name} on {snapshot_date_only}")
        return True

    @staticmethod
    def _aggregate_holdings(wallets, snapshot_date: datetime) -> tuple[dict[str, Any], Decimal]:
        snapshot_date_only = snapshot_date.date()
        holdings_data = {}

        for wallet in wallets:
            snapshots = (
                HoldingSnapshot.objects.filter_by_wallet(wallet)
                .filter(holding__asset__is_active=True)
                .filter_by_date_range(end_date=snapshot_date)
                .with_optimized_data()
                .order_by("holding__asset_id", "-snapshot_date")
            )

            seen_assets = set()
            for snap in snapshots:
                if snap.holding.asset_id in seen_assets:
                    continue
                seen_assets.add(snap.holding.asset_id)

                asset = snap.holding.asset
                symbol = asset.symbol

                if symbol not in holdings_data:
                    holdings_data[symbol] = {
                        "asset": asset,
                        "asset_uuid": str(asset.uuid),
                        "quantity": Decimal("0"),
                        "wallets": [],
                    }

                holdings_data[symbol]["quantity"] += snap.quantity or Decimal("0")
                holdings_data[symbol]["wallets"].append(str(wallet.uuid))

        total_value = Decimal("0")
        result = {}

        for symbol, data in holdings_data.items():
            asset = data["asset"]
            quantity = data["quantity"]

            result[symbol] = {
                "asset_uuid": data["asset_uuid"],
                "quantity": str(quantity),
                "wallets": data["wallets"],
            }

            price_snapshot = (
                AssetSnapshot.objects.filter_by_asset(asset.uuid)
                .filter_by_date_range(end_date=snapshot_date_only)
                .order_by("-source_timestamp")
                .first()
            )

            if price_snapshot:
                market_value = quantity * price_snapshot.price
                total_value += market_value
                result[symbol]["price"] = str(price_snapshot.price)
                result[symbol]["market_value"] = str(market_value)
                result[symbol]["price_snapshot_uuid"] = str(price_snapshot.uuid)

        return result, total_value
