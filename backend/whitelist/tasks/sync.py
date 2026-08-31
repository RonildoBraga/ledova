import logging

from procrastinate import RetryStrategy
from rest_framework.exceptions import APIException

from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


@app.periodic(cron="*/30 * * * *")
@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def sync_all_entries(timestamp: int):
    """Sync the on-chain whitelist registry. Runs every 30 minutes."""
    from whitelist.services import WhitelistService

    service = WhitelistService()
    count = service.sync_all_entries()
    logger.info(f"{LoggingContext.WHITELIST_SYNC} Synced {count} entries")
    return {"synced": count}


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def sync_entry(address: str):
    from whitelist.services import WhitelistService

    service = WhitelistService()
    entry = service.sync_entry(address)
    logger.info(f"{LoggingContext.WHITELIST_SYNC} Synced entry {address}: {entry.status}")
    return {"address": address, "status": entry.status}


@app.task
def add_to_whitelist_async(address: str):
    from whitelist.services import WhitelistService

    try:
        service = WhitelistService()
        tx_hash, entry = service.add_to_whitelist(
            address=address,
            wait_for_receipt=True,
        )
        logger.info(f"{LoggingContext.WHITELIST_SYNC} Added {address} to whitelist (tx={tx_hash})")
        return {"success": True, "tx_hash": tx_hash, "address": address}
    except APIException as e:
        logger.error(f"{LoggingContext.WHITELIST_SYNC} Failed to add {address}: {e}")
        return {"success": False, "error": str(e.detail), "address": address}


@app.task
def remove_from_whitelist_async(address: str):
    from whitelist.services import WhitelistService

    try:
        service = WhitelistService()
        tx_hash, entry = service.remove_from_whitelist(
            address=address,
            wait_for_receipt=True,
        )
        logger.info(f"{LoggingContext.WHITELIST_SYNC} Removed {address} from whitelist (tx={tx_hash})")
        return {"success": True, "tx_hash": tx_hash, "address": address}
    except APIException as e:
        logger.error(f"{LoggingContext.WHITELIST_SYNC} Failed to remove {address}: {e}")
        return {"success": False, "error": str(e.detail), "address": address}
