import logging
import time
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment, AssetSnapshot, AssetType
from integrations.coingecko import SYMBOL_TO_COINGECKO_ID, CoinGeckoClient
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")

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

INCEPTION_DATES = {
    "BTC": datetime(2013, 4, 1, tzinfo=dt_timezone.utc),
    "ETH": datetime(2015, 7, 30, tzinfo=dt_timezone.utc),
}


class AssetSyncService:
    @staticmethod
    def sync_assets(
        backfill_days: int = 365,
        today_only: bool = False,
    ) -> Dict[str, Any]:
        logger.info(
            f"{LoggingContext.ASSETS} Starting asset sync " f"(today_only={today_only}, backfill_days={backfill_days})"
        )

        result = {
            "status": "success",
            "assets_created": 0,
            "assets_updated": 0,
            "prices_updated": 0,
            "snapshots_created": 0,
            "historical_snapshots": 0,
            "operations_completed": [],
        }

        try:
            logger.info(f"{LoggingContext.ASSETS} Step 1: Creating/updating assets")
            asset_result = AssetSyncService._create_or_update_assets()
            result["assets_created"] = asset_result["created"]
            result["assets_updated"] = asset_result["updated"]
            result["operations_completed"].append("asset_creation")

            logger.info(f"{LoggingContext.ASSETS} Step 2: Syncing current prices from CoinGecko")
            price_result = AssetSyncService._sync_current_prices()
            result["prices_updated"] = price_result["updated"]
            result["snapshots_created"] = price_result["snapshots_created"]
            result["operations_completed"].append("price_sync")

            if not today_only:
                logger.info(f"{LoggingContext.ASSETS} Step 3: Backfilling historical prices ({backfill_days} days)")
                backfill_result = AssetSyncService._backfill_historical_prices(days=backfill_days)
                result["historical_snapshots"] = backfill_result["snapshots_created"]
                result["operations_completed"].append("historical_backfill")

            logger.info(
                f"{LoggingContext.ASSETS} Asset sync completed - "
                f"Assets: {result['assets_created']} created, {result['assets_updated']} updated | "
                f"Prices: {result['prices_updated']} updated | "
                f"Snapshots: {result['snapshots_created']} current, {result['historical_snapshots']} historical"
            )

            return result

        except Exception as e:
            logger.error(f"{LoggingContext.ASSETS} Asset sync failed: {e.__class__.__name__}: {str(e)}")
            result["status"] = "error"
            result["error"] = f"{e.__class__.__name__}: {str(e)}"
            return result

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
                today_midnight = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
                snapshot, _ = AssetSnapshot.objects.update_or_create(
                    asset=asset,
                    source_timestamp=today_midnight,
                    defaults={"price": price, "price_currency": currency, "data_source": source},
                )

            return snapshot

    @staticmethod
    def get_price_history(
        asset: Asset,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[AssetSnapshot]:
        queryset = AssetSnapshot.objects.filter(asset=asset)

        if start_date:
            queryset = queryset.filter(source_timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(source_timestamp__lte=end_date)

        queryset = queryset.order_by("-source_timestamp")

        if limit:
            queryset = queryset[:limit]

        return list(queryset)

    @staticmethod
    def _create_or_update_assets() -> Dict[str, int]:
        created_count = 0
        updated_count = 0
        failed_count = 0

        for symbol, metadata in SUPPORTED_ASSETS.items():
            try:
                asset, created = Asset.objects.get_or_create(
                    symbol=symbol,
                    defaults={
                        "name": metadata["name"],
                        "asset_type": metadata["type"].value,
                        "decimals": metadata["decimals"],
                        "is_active": True,
                        "is_verified": True,
                    },
                )

                if created:
                    logger.info(f"{LoggingContext.ASSETS} Created asset: {symbol} - {metadata['name']}")
                    created_count += 1
                else:
                    asset.name = metadata["name"]
                    asset.asset_type = metadata["type"].value
                    asset.decimals = metadata["decimals"]
                    asset.is_verified = True
                    asset.save()
                    updated_count += 1

                deployments = metadata.get("deployments", [])
                if not deployments and metadata.get("chain"):
                    deployments = [
                        {
                            "chain": metadata["chain"],
                            "contract": metadata.get("contract"),
                            "decimals": metadata["decimals"],
                        }
                    ]
                for dep in deployments:
                    AssetChainDeployment.objects.update_or_create(
                        asset=asset,
                        chain=dep["chain"],
                        defaults={
                            "contract_address": dep.get("contract"),
                            "decimals": dep.get("decimals", metadata["decimals"]),
                            "is_active": True,
                        },
                    )

            except Exception as e:
                logger.error(f"{LoggingContext.ASSETS} Failed to create/update {symbol}: {str(e)}")
                failed_count += 1

        logger.info(
            f"{LoggingContext.ASSETS} Asset creation completed - "
            f"Created: {created_count}, Updated: {updated_count}, Failed: {failed_count}"
        )

        return {"created": created_count, "updated": updated_count, "failed": failed_count}

    @staticmethod
    def _sync_current_prices() -> Dict[str, int]:
        crypto_assets = Asset.objects.filter(
            is_active=True,
            asset_type__in=["native_crypto", "stablecoin", "erc20_token", "tokenized_rwa"],
        )

        if not crypto_assets.exists():
            return {"updated": 0, "failed": 0, "snapshots_created": 0, "snapshots_updated": 0}

        symbols = list(crypto_assets.values_list("symbol", flat=True))
        logger.info(f"{LoggingContext.ASSETS} Fetching prices for {len(symbols)} assets from CoinGecko")

        today_midnight = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for symbol in symbols:
            metadata = SUPPORTED_ASSETS.get(symbol, {})
            fixed_price = metadata.get("fixed_price")
            nav_price = metadata.get("nav_price")
            if fixed_price:
                try:
                    asset = Asset.objects.get(symbol=symbol)
                    asset.current_price = fixed_price
                    asset.price_currency = "USD"
                    asset.save(update_fields=["current_price", "price_currency", "updated_at"])
                    AssetSnapshot.objects.update_or_create(
                        asset=asset,
                        source_timestamp=today_midnight,
                        defaults={
                            "price": fixed_price,
                            "price_currency": "USD",
                            "market_data": {},
                            "data_source": "fixed_peg",
                        },
                    )
                except Asset.DoesNotExist:
                    pass
            elif nav_price:
                try:
                    asset = Asset.objects.get(symbol=symbol)
                    if not asset.current_price:
                        from tokens.models import YieldToken

                        yt = YieldToken.objects.filter(symbol=symbol, is_active=True).first()
                        if yt and yt.nav_per_token:
                            asset.current_price = yt.nav_per_token
                            asset.price_currency = "USD"
                            asset.save(update_fields=["current_price", "price_currency", "updated_at"])
                    if asset.current_price:
                        AssetSnapshot.objects.update_or_create(
                            asset=asset,
                            source_timestamp=today_midnight,
                            defaults={
                                "price": asset.current_price,
                                "price_currency": "USD",
                                "market_data": {},
                                "data_source": "nav_update",
                            },
                        )
                except Asset.DoesNotExist:
                    pass

        symbol_map = {}
        for symbol in symbols:
            symbol_upper = symbol.upper()
            if symbol_upper in SYMBOL_TO_COINGECKO_ID:
                symbol_map[symbol_upper] = SYMBOL_TO_COINGECKO_ID[symbol_upper]

        if not symbol_map:
            return {"updated": 0, "failed": 0, "snapshots_created": 0, "snapshots_updated": 0}

        try:
            client = CoinGeckoClient()
            price_data = client.fetch_prices_by_symbols(symbol_map)
        except Exception as e:
            logger.error(f"{LoggingContext.ASSETS} Failed to fetch prices from CoinGecko: {str(e)}")
            return {"updated": 0, "failed": 0, "snapshots_created": 0, "snapshots_updated": 0}

        if not price_data:
            return {"updated": 0, "failed": 0, "snapshots_created": 0, "snapshots_updated": 0}

        updated_count = 0
        failed_count = 0
        snapshots_created = 0
        snapshots_updated = 0

        for symbol, data in price_data.items():
            try:
                asset = Asset.objects.get(symbol=symbol)
                price = Decimal(str(data["price"]))

                asset.current_price = price
                asset.price_currency = "USD"
                asset.save(update_fields=["current_price", "price_currency", "updated_at"])
                updated_count += 1

                snapshot, created = AssetSnapshot.objects.update_or_create(
                    asset=asset,
                    source_timestamp=today_midnight,
                    defaults={
                        "price": price,
                        "price_currency": "USD",
                        "market_data": {},
                        "data_source": "coingecko",
                    },
                )

                if created:
                    snapshots_created += 1
                else:
                    snapshots_updated += 1

            except Asset.DoesNotExist:
                failed_count += 1
            except (ValueError, InvalidOperation) as e:
                logger.error(f"{LoggingContext.ASSETS} Invalid price for {symbol}: {str(e)}")
                failed_count += 1
            except Exception as e:
                logger.error(f"{LoggingContext.ASSETS} Failed to update {symbol}: {str(e)}")
                failed_count += 1

        logger.info(
            f"{LoggingContext.ASSETS} Price sync completed - "
            f"Updated: {updated_count}, Failed: {failed_count}, "
            f"Snapshots: {snapshots_created} created, {snapshots_updated} updated"
        )

        return {
            "updated": updated_count,
            "failed": failed_count,
            "snapshots_created": snapshots_created,
            "snapshots_updated": snapshots_updated,
        }

    @staticmethod
    def _backfill_historical_prices(days: int = 365) -> Dict[str, Any]:
        symbols = list(SUPPORTED_ASSETS.keys())
        logger.info(f"{LoggingContext.ASSETS} Backfilling {len(symbols)} supported assets: {symbols}")

        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        total_snapshots = 0
        assets_processed = 0
        assets_failed = 0

        for symbol in symbols:
            try:
                asset = Asset.objects.get(symbol=symbol)
            except Asset.DoesNotExist:
                logger.warning(f"{LoggingContext.ASSETS} Asset not found for backfill: {symbol}")
                assets_failed += 1
                continue

            coin_id = SYMBOL_TO_COINGECKO_ID.get(symbol.upper())
            if not coin_id:
                logger.warning(f"{LoggingContext.ASSETS} No CoinGecko ID for {symbol}")
                assets_failed += 1
                continue

            existing_count = AssetSnapshot.objects.filter(
                asset=asset,
                source_timestamp__gte=start_date,
                source_timestamp__lte=end_date,
            ).count()

            coverage_percent = (existing_count / days * 100) if days > 0 else 0

            if coverage_percent >= 95:
                logger.info(
                    f"{LoggingContext.ASSETS} {symbol} already has {coverage_percent:.1f}% coverage "
                    f"({existing_count}/{days} days), skipping"
                )
                assets_processed += 1
                continue

            try:
                client = CoinGeckoClient()
                price_data = client.fetch_historical_prices_bulk(coin_id, start_date, end_date)

                if not price_data:
                    assets_failed += 1
                    continue

                daily_prices: Dict[datetime, Decimal] = {}
                for data_point in price_data:
                    ts = data_point["timestamp"]
                    price = data_point["price"]
                    day_midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
                    daily_prices[day_midnight] = price

                snapshots_to_create = []
                for day_midnight, price in daily_prices.items():
                    exists = AssetSnapshot.objects.filter(
                        asset=asset,
                        source_timestamp=day_midnight,
                    ).exists()

                    if not exists:
                        snapshots_to_create.append(
                            AssetSnapshot(
                                asset=asset,
                                price=price,
                                price_currency="USD",
                                source_timestamp=day_midnight,
                                data_source="coingecko_historical",
                                market_data={},
                            )
                        )

                if snapshots_to_create:
                    AssetSnapshot.objects.bulk_create(snapshots_to_create, ignore_conflicts=True)
                    total_snapshots += len(snapshots_to_create)
                    logger.info(
                        f"{LoggingContext.ASSETS} Created {len(snapshots_to_create)} daily snapshots for {symbol}"
                    )

                assets_processed += 1
                time.sleep(2)

            except Exception as e:
                logger.error(f"{LoggingContext.ASSETS} Failed to backfill {symbol}: {str(e)}")
                assets_failed += 1

        logger.info(
            f"{LoggingContext.ASSETS} Historical backfill completed - "
            f"Assets: {assets_processed} processed, {assets_failed} failed | "
            f"Snapshots: {total_snapshots} created"
        )

        return {
            "assets_processed": assets_processed,
            "assets_failed": assets_failed,
            "snapshots_created": total_snapshots,
        }
