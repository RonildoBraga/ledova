import logging
from typing import Any, Dict

from procrastinate import RetryStrategy

from assets.models import Asset
from assets.services import AssetSyncService
from assets.services.sync import SUPPORTED_ASSETS
from ledova_backend.procrastinate_app import app

logger = logging.getLogger(__name__)


@app.periodic(cron="*/10 * * * *")
@app.task(name="assets.sync_all_assets", retry=RetryStrategy(max_attempts=4, wait=300))
def sync_all_assets(timestamp: int, today_only: bool = True) -> Dict[str, Any]:
    """Sync all assets from CoinGecko. Runs every 10 minutes.

    By default, only syncs current prices for efficiency. Set today_only=False
    when invoked manually to include historical backfill.
    """
    logger.info(f"Starting asset sync task (today_only={today_only})")
    if Asset.objects.filter(symbol__in=SUPPORTED_ASSETS).count() < len(SUPPORTED_ASSETS):
        AssetSyncService.ensure_supported_assets()
    return AssetSyncService.sync_assets(today_only=today_only)
