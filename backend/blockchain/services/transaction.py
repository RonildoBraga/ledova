import json
import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone
from web3 import Web3

from shared.db import atomic

logger = logging.getLogger(__name__)


def _submission_identity(tx):
    return (
        tx.tx_hash,
        tx.status,
        tx.tx_type,
        tx.from_address,
        tx.to_address,
        tx.value,
        tx.gas_limit,
        tx.gas_price,
        tx.nonce,
        tx.function_name,
        json.dumps(tx.function_args, sort_keys=True),
        tx.related_model,
        tx.related_uuid,
        tx.submitted_at,
    )


def _receipt_matches(receipt, requested_hash):
    if "transactionHash" not in receipt:
        return True
    receipt_hash = receipt["transactionHash"]
    if isinstance(receipt_hash, bytes):
        receipt_hash = receipt_hash.hex()
    if not isinstance(receipt_hash, str):
        return False
    return receipt_hash.lower().removeprefix("0x") == requested_hash.lower().removeprefix("0x")


def _record_receipt(expected, receipt):
    from blockchain.models import BlockchainTransaction, TransactionStatus

    with atomic():
        current = BlockchainTransaction.objects.select_for_update(of=("self",)).filter(pk=expected.pk).first()
        if current is None or not current.is_pending or _submission_identity(current) != _submission_identity(expected):
            return None
        if receipt["status"] == 1:
            current.mark_confirmed(
                block_number=receipt["blockNumber"],
                block_hash=(
                    Web3.to_hex(receipt["blockHash"])
                    if hasattr(receipt["blockHash"], "hex")
                    else str(receipt["blockHash"])
                ),
                gas_used=receipt["gasUsed"],
            )
            logger.info("Confirmed tx %s...", current.tx_hash[:10])
            return TransactionStatus.CONFIRMED
        current.mark_reverted("Transaction reverted on-chain")
        logger.warning("Reverted tx %s...", current.tx_hash[:10])
        return TransactionStatus.REVERTED


class TransactionMonitorService:
    @staticmethod
    def check_pending_transactions(chain_client) -> dict[str, Any]:
        from blockchain.models import BlockchainTransaction, TransactionStatus

        pending = BlockchainTransaction.objects.pending().with_tx_hash()

        checked = 0
        confirmed = 0
        failed = 0

        for tx in pending:
            try:
                receipt = chain_client.get_transaction_receipt(tx.tx_hash)
                if receipt:
                    status = receipt.get("status")
                    if isinstance(status, bool) or not isinstance(status, int) or status not in (0, 1):
                        logger.info("Retained tx %s with unavailable receipt outcome", tx.tx_hash[:10])
                    elif not _receipt_matches(receipt, tx.tx_hash):
                        logger.info("Retained tx %s with conflicting receipt identity", tx.tx_hash[:10])
                    else:
                        outcome = _record_receipt(tx, receipt)
                        confirmed += outcome == TransactionStatus.CONFIRMED
                        failed += outcome == TransactionStatus.REVERTED
                checked += 1
            except Exception as e:
                logger.error(f"Error checking tx {tx.tx_hash}: {e}")

        logger.info(f"Checked {checked} transactions: {confirmed} confirmed, {failed} failed")
        return {"checked": checked, "confirmed": confirmed, "failed": failed}

    @staticmethod
    def cleanup_stale_transactions(hours: int = 24) -> dict[str, Any]:
        from blockchain.models import BlockchainTransaction

        cutoff = timezone.now() - timedelta(hours=hours)
        overdue = BlockchainTransaction.objects.stale(cutoff).count()

        logger.info("Retained %s overdue transactions for receipt recovery", overdue)
        return {"cleaned": 0, "overdue": overdue}
