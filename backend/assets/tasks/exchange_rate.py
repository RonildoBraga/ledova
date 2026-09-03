import logging

from procrastinate import RetryStrategy

from assets.services import ExchangeRateService
from ledova_backend.procrastinate_app import app

logger = logging.getLogger(__name__)


@app.periodic(cron="*/10 * * * *")
@app.task(name="assets.sync_exchange_rates", retry=RetryStrategy(max_attempts=4, wait=300))
def sync_exchange_rates(timestamp: int) -> dict:
    """Sync fiat exchange rates from CoinGecko. Runs every 10 minutes."""
    logger.info("Starting exchange rate sync")
    result = ExchangeRateService.sync_exchange_rates()
    logger.info(f"Exchange rate sync completed - {result['updated']}/{result['total']} rates updated")
    return result
