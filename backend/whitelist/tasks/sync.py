import logging

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app

logger = logging.getLogger(__name__)


@app.periodic(cron="*/30 * * * *")
@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def sync_all_entries(timestamp: int):
    from whitelist.services import WhitelistService

    service = WhitelistService()
    count = service.sync_all_entries()
    logger.info(f"Synced {count} entries")
    return {"synced": count}


@app.periodic(cron="*/30 * * * *")
@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def reconcile_failed_adds(timestamp: int):
    from whitelist.services import WhitelistService

    result = WhitelistService().reconcile_failed_adds()
    if result["activated"] or result["errors"]:
        logger.warning(
            f"Whitelist reconciliation: {result['activated']} activated of {result['checked']} checked, "
            f"{len(result['errors'])} unreadable"
        )
    return result
