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


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def sync_entry(address: str):
    from whitelist.services import WhitelistService

    service = WhitelistService()
    entry = service.sync_entry(address)
    logger.info(f"Synced entry {address}: {entry.status}")
    return {"address": address, "status": entry.status}
