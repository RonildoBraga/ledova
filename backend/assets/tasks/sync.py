import logging
from typing import Any, Dict

from procrastinate import RetryStrategy

from assets.services import AssetSyncService
from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


@app.periodic(cron="*/10 * * * *")
@app.task(name="assets.sync_all_assets", retry=RetryStrategy(max_attempts=4, wait=300))
def sync_all_assets(timestamp: int, today_only: bool = True) -> Dict[str, Any]:
    """Sync all assets from CoinGecko. Runs every 10 minutes.

    By default, only syncs current prices for efficiency. Set today_only=False
    when invoked manually to include historical backfill.
    """
    logger.info(f"{LoggingContext.ASSETS} Starting asset sync task (today_only={today_only})")
    result = AssetSyncService.sync_assets(today_only=today_only)

    if result["status"] == "success":
        logger.info(
            f"{LoggingContext.ASSETS} Asset sync completed - "
            f"Assets: {result['assets_created']} created, {result['assets_updated']} updated | "
            f"Prices: {result['prices_updated']} updated | "
            f"Snapshots: {result['snapshots_created']} current, {result['historical_snapshots']} historical"
        )

    return result
