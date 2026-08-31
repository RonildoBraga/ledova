import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from blockchain.exceptions import (
    MaxRetryCountReachedException,
    TransactionNotFailedException,
    TransactionNotFoundException,
)
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

    @staticmethod
    @transaction.atomic
    def retry_transaction(transaction_uuid: str) -> dict[str, Any]:
        from blockchain.models import BlockchainTransaction, TransactionStatus

        try:
            tx = BlockchainTransaction.objects.select_for_update().get(uuid=transaction_uuid)
        except BlockchainTransaction.DoesNotExist:
            logger.error(f"{LoggingContext.BLOCKCHAIN_TX} Transaction {transaction_uuid} not found")
            raise TransactionNotFoundException()

        if tx.status not in [TransactionStatus.FAILED, TransactionStatus.REVERTED]:
            raise TransactionNotFailedException(f"Transaction is not in failed state: {tx.status}")

        if tx.retry_count >= 3:
            raise MaxRetryCountReachedException()

        tx.status = TransactionStatus.PENDING
        tx.retry_count += 1
        tx.error_message = ""
        tx.save(update_fields=["status", "retry_count", "error_message", "updated_at"])

        logger.info(
            f"{LoggingContext.BLOCKCHAIN_TX} Reset transaction {tx.tx_hash or tx.uuid} "
            f"for retry (attempt {tx.retry_count})"
        )

        return {"success": True, "retry_count": tx.retry_count}
