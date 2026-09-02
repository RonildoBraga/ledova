import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


class TransactionMonitorService:
    @staticmethod
    def check_pending_transactions(chain_client) -> dict[str, Any]:
        from blockchain.models import BlockchainTransaction

        pending = BlockchainTransaction.objects.pending().with_tx_hash()

        checked = 0
        confirmed = 0
        failed = 0

        for tx in pending:
            try:
                receipt = chain_client.get_transaction_receipt(tx.tx_hash)
                if receipt:
                    if receipt.get("status") == 1:
                        tx.mark_confirmed(
                            block_number=receipt["blockNumber"],
                            block_hash=(
                                receipt["blockHash"].hex()
                                if hasattr(receipt["blockHash"], "hex")
                                else str(receipt["blockHash"])
                            ),
                            gas_used=receipt["gasUsed"],
                        )
                        confirmed += 1
                        logger.info(f"{LoggingContext.BLOCKCHAIN_TX} Confirmed tx {tx.tx_hash[:10]}...")
                    else:
                        tx.mark_reverted("Transaction reverted on-chain")
                        failed += 1
                        logger.warning(f"{LoggingContext.BLOCKCHAIN_TX} Reverted tx {tx.tx_hash[:10]}...")
                checked += 1
            except Exception as e:
                logger.error(f"{LoggingContext.BLOCKCHAIN_TX} Error checking tx {tx.tx_hash}: {e}")

        logger.info(
            f"{LoggingContext.BLOCKCHAIN_TX} Checked {checked} transactions: " f"{confirmed} confirmed, {failed} failed"
        )
        return {"checked": checked, "confirmed": confirmed, "failed": failed}

    @staticmethod
    @transaction.atomic
    def cleanup_stale_transactions(hours: int = 24) -> dict[str, Any]:
        from blockchain.models import BlockchainTransaction

        cutoff = timezone.now() - timedelta(hours=hours)
        stale = BlockchainTransaction.objects.stale(cutoff)

        count = 0
        for tx in stale:
            tx.mark_failed(f"Transaction timed out after {hours} hours")
            count += 1

        logger.info(f"{LoggingContext.BLOCKCHAIN_TX} Marked {count} stale transactions as failed")
        return {"cleaned": count}
