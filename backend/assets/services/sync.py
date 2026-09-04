import logging
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment, AssetSnapshot, AssetType
from integrations.coingecko import SYMBOL_TO_COINGECKO_ID, CoinGeckoClient

logger = logging.getLogger(__name__)

SUPPORTED_ASSETS = {
    "BTC": {
        "coingecko_id": "bitcoin",
        "name": "Bitcoin",
        "type": AssetType.NATIVE_CRYPTO,
        "chain": "bitcoin",
        "decimals": 8,
    },
    "ETH": {
        "coingecko_id": "ethereum",
        "name": "Ethereum",
        "type": AssetType.NATIVE_CRYPTO,
        "chain": "ethereum",
        "decimals": 18,
    },
    "USDC": {
        "coingecko_id": "usd-coin",
        "name": "USD Coin",
        "type": AssetType.STABLECOIN,
        "chain": "ethereum",
        "decimals": 6,
    },
    "USDT": {
        "coingecko_id": "tether",
        "name": "Tether",
        "type": AssetType.STABLECOIN,
        "chain": "ethereum",
        "decimals": 6,
    },
    "AUDY": {
        "coingecko_id": None,
        "name": "AUDY",
        "type": AssetType.STABLECOIN,
        "chain": "ethereum",
        "decimals": 2,
        "fixed_price": Decimal("1.00"),
    },
    "AUSG": {
        "coingecko_id": None,
        "name": "AUSG",
        "type": AssetType.TOKENIZED_RWA,
        "chain": "base",
        "decimals": 6,
        "nav_price": True,
    },
}

PRICED_ASSET_TYPES = ("native_crypto", "stablecoin", "erc20_token", "tokenized_rwa")


def _midnight(moment) -> Any:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


class AssetSyncService:
    @staticmethod
    def sync_assets(backfill_days: int = 365, today_only: bool = False) -> Dict[str, Any]:
        logger.info(f"Starting asset sync (today_only={today_only}, backfill_days={backfill_days})")
        try:
            result = {
                "status": "success",
                "prices_updated": AssetSyncService._sync_current_prices(),
                "historical_snapshots": 0,
            }
            if not today_only:
                result["historical_snapshots"] = AssetSyncService._backfill_historical_prices(days=backfill_days)
            logger.info(
                f"Asset sync completed - prices: {result['prices_updated']} updated, "
                f"historical snapshots: {result['historical_snapshots']} created"
            )
            return result
        except Exception as e:
            logger.error(f"Asset sync failed: {e.__class__.__name__}: {str(e)}")
            return {"status": "error", "error": f"{e.__class__.__name__}: {str(e)}"}

    @staticmethod
    def ensure_supported_assets() -> None:
        """Upsert the SUPPORTED_ASSETS rows and their chain deployments. Never re-activates an asset
        the admin switched off and never overwrites a hand-entered contract address."""
        for symbol, meta in SUPPORTED_ASSETS.items():
            asset, _ = Asset.objects.update_or_create(
                symbol=symbol,
                defaults={
                    "name": meta["name"],
                    "asset_type": meta["type"].value,
                    "decimals": meta["decimals"],
                    "is_verified": True,
                },
            )
            AssetChainDeployment.objects.update_or_create(
                asset=asset, chain=meta["chain"], defaults={"decimals": meta["decimals"], "is_active": True}
            )

    @staticmethod
    def update_price(
        asset: Asset,
        price: Decimal,
        source: str = "manual",
        currency: str = "USD",
        create_snapshot: bool = True,
    ) -> Optional[AssetSnapshot]:
        if price <= 0:
            raise ValueError(f"Price must be positive, got {price}")

        with transaction.atomic():
            asset.current_price = price
            asset.price_currency = currency
            asset.save(update_fields=["current_price", "price_currency", "updated_at"])

            snapshot = None
            if create_snapshot:
                # One row per asset per day: a manual price overwrites today's midnight row
                # (same key the periodic sync writes) instead of adding an intraday duplicate.
                # market_data is deliberately not in defaults so an existing NAV row keeps its provenance.
                snapshot, _ = AssetSnapshot.objects.update_or_create(
                    asset=asset,
                    source_timestamp=_midnight(timezone.now()),
                    defaults={"price": price, "price_currency": currency, "data_source": source},
                )

            return snapshot

    @staticmethod
    def _current_prices() -> Dict[str, Tuple[Decimal, str]]:
        """(price, data_source) per symbol: fixed pegs, yield-token NAVs, then one CoinGecko call
        for every active priced asset the symbol map knows."""
        from tokens.models import YieldToken

        prices: Dict[str, Tuple[Decimal, str]] = {}
        for symbol, meta in SUPPORTED_ASSETS.items():
            if meta.get("fixed_price"):
                prices[symbol] = (meta["fixed_price"], "fixed_peg")
            elif meta.get("nav_price"):
                nav = YieldToken.objects.filter(symbol=symbol, is_active=True).values_list("nav_per_token", flat=True)
                if nav and nav[0]:
                    prices[symbol] = (nav[0], "nav_update")

        symbols = Asset.objects.filter(is_active=True, asset_type__in=PRICED_ASSET_TYPES).values_list(
            "symbol", flat=True
        )
        symbol_map = {symbol: SYMBOL_TO_COINGECKO_ID[symbol] for symbol in symbols if symbol in SYMBOL_TO_COINGECKO_ID}
        if symbol_map:
            try:
                for symbol, data in CoinGeckoClient().fetch_prices_by_symbols(symbol_map).items():
                    prices[symbol] = (Decimal(str(data["price"])), "coingecko")
            except Exception as e:
                logger.error(f"Failed to fetch prices from CoinGecko: {str(e)}")
        return prices

    @staticmethod
    def _sync_current_prices() -> int:
        prices = AssetSyncService._current_prices()
        updated = 0
        for asset in Asset.objects.filter(symbol__in=prices, is_active=True):
            price, source = prices[asset.symbol]
            try:
                AssetSyncService.update_price(asset, price, source=source)
                updated += 1
            except Exception as e:
                logger.error(f"Failed to update {asset.symbol}: {str(e)}")
        logger.info(f"Price sync completed - {updated} of {len(prices)} prices written")
        return updated

    @staticmethod
    def _backfill_historical_prices(days: int = 365) -> int:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        created = 0

        for asset in Asset.objects.filter(symbol__in=SUPPORTED_ASSETS):
            coin_id = SYMBOL_TO_COINGECKO_ID.get(asset.symbol)
            if not coin_id:
                continue

            existing = set(
                AssetSnapshot.objects.filter(
                    asset=asset, source_timestamp__gte=_midnight(start_date), source_timestamp__lte=end_date
                ).values_list("source_timestamp", flat=True)
            )
            if days > 0 and len(existing) / days >= 0.95:
                logger.info(f"{asset.symbol} already has {len(existing)}/{days} days, skipping")
                continue

            try:
                price_data = CoinGeckoClient().fetch_historical_prices_bulk(coin_id, start_date, end_date)
            except Exception as e:
                logger.error(f"Failed to backfill {asset.symbol}: {str(e)}")
                continue

            daily_prices = {_midnight(point["timestamp"]): point["price"] for point in price_data}
            snapshots = [
                AssetSnapshot(
                    asset=asset,
                    price=price,
                    price_currency="USD",
                    source_timestamp=day,
                    data_source="coingecko_historical",
                    market_data={},
                )
                for day, price in daily_prices.items()
                if day not in existing
            ]
            if snapshots:
                AssetSnapshot.objects.bulk_create(snapshots, ignore_conflicts=True)
                created += len(snapshots)
                logger.info(f"Created {len(snapshots)} daily snapshots for {asset.symbol}")
            time.sleep(2)

        logger.info(f"Historical backfill completed - {created} snapshots created")
        return created
