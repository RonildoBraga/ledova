import logging
from typing import Any, Dict

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from wallets.services.sync import WalletSyncService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def sync_wallet(wallet_uuid: str) -> Dict[str, Any]:
    try:
        wallet = Wallet.objects.get(uuid=wallet_uuid)
    except Wallet.DoesNotExist:
        logger.error(f"Wallet not found: {wallet_uuid}")
        return {"status": "error", "error": "Wallet not found"}

    result = WalletSyncService.sync_wallet(wallet)
    if result["status"] == "success":
        logger.info(f"{wallet_uuid}: tx={result.get('transactions', 0)}, holdings={result.get('holdings', 0)}")
    return result


@app.periodic(cron="0 * * * *")
@app.task
def sync_all_wallets(timestamp: int) -> Dict[str, Any]:
    wallets = Wallet.objects.filter(verification_status=WALLET_VERIFICATION_STATUS_VERIFIED)
    total = wallets.count()
    queued = 0

    for wallet in wallets:
        try:
            sync_wallet.defer(wallet_uuid=str(wallet.uuid))
            queued += 1
        except Exception as e:
            logger.error(f"Queue failed {wallet.uuid}: {e}")

    logger.info(f"Queued {queued}/{total} wallets")
    return {"total": total, "queued": queued}
