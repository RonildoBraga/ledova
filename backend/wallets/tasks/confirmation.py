import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Dict

from django.db.models import Q
from django.utils import timezone
from procrastinate import RetryStrategy

from integrations.blockchain import get_blockchain_client
from integrations.blockchain.receipts import transaction_hash_matches
from ledova_backend.procrastinate_app import app
from shared.constants import BLOCKCHAIN_BITCOIN
from shared.db import acting_for
from wallets.constants import TRANSACTION_STATUS_PENDING
from wallets.models import Transaction, Wallet
from wallets.services import transaction_confirmation
from wallets.services.history_receipts import record_history_receipt
from wallets.services.receipt_readers import extract_actual_fee, get_receipt_reader
from wallets.services.receipt_targets import capture_receipt_target

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=6, wait=30))
def confirm_pending_transaction(tx_hash: str, wallet_uuid: str, *, principal_id) -> Dict[str, Any]:
    with acting_for(principal_id):
        return _confirm_pending_transaction(tx_hash, wallet_uuid)


def _confirm_pending_transaction(tx_hash: str, wallet_uuid: str) -> Dict[str, Any]:
    try:
        wallet = Wallet.objects.get(uuid=wallet_uuid)
    except Wallet.DoesNotExist:
        logger.error(f"Wallet not found: {wallet_uuid}")
        return {"status": "error", "error": "Wallet not found"}

    try:
        tx = Transaction.objects.get(tx_hash=tx_hash, wallet=wallet)
        if tx.status != TRANSACTION_STATUS_PENDING:
            if tx.balance_reconciliation_token is not None:
                repaired = transaction_confirmation.reconcile_transaction(tx_hash, wallet=wallet)
                return {"status": "reconciled" if repaired else "reconciliation_pending", "tx_hash": tx_hash}
            logger.info(f"Transaction already processed: {tx_hash}")
            return {"status": "already_processed", "current_status": tx.status}
    except Transaction.DoesNotExist:
        return {"status": "not_found", "tx_hash": tx_hash}

    expected = capture_receipt_target(wallet, tx)
    client = get_blockchain_client(wallet.chain)
    receipt = client.get_transaction_receipt(tx_hash)

    if receipt is None:
        logger.info(f"Transaction not yet confirmed: {tx_hash}")
        raise RuntimeError(f"receipt not yet available for {tx_hash}")

    hash_field = "tx_hash" if wallet.chain.lower() == BLOCKCHAIN_BITCOIN else "transactionHash"
    if not isinstance(receipt, Mapping) or not transaction_hash_matches(receipt.get(hash_field), tx_hash):
        raise RuntimeError(f"receipt identity not yet available for {tx_hash}")

    reader = get_receipt_reader(wallet.chain)
    succeeded = reader.succeeded(receipt)
    if succeeded is None:
        raise RuntimeError(f"receipt outcome not yet available for {tx_hash}")

    block_number = reader.block_number(receipt)
    block_hash = reader.block_hash(receipt)
    block_timestamp = reader.block_timestamp(client, receipt, block_number)
    actual_fee = extract_actual_fee(receipt, wallet.chain)

    if tx.imported_from_history:
        return record_history_receipt(
            tx_hash,
            wallet=wallet,
            succeeded=succeeded,
            block_number=block_number,
            block_hash=block_hash,
            block_timestamp=block_timestamp,
            actual_fee=actual_fee,
            expected=expected,
        )

    if succeeded:
        result = transaction_confirmation.confirm_transaction(
            tx_hash=tx_hash,
            wallet=wallet,
            block_number=block_number,
            block_hash=block_hash,
            block_timestamp=block_timestamp,
            actual_fee=actual_fee,
            expected=expected,
        )
        if result["status"] == "confirmed":
            logger.info(f"Transaction confirmed: {tx_hash}, actual_fee={actual_fee}")
    else:
        result = transaction_confirmation.fail_transaction(
            tx_hash=tx_hash,
            wallet=wallet,
            reason="Transaction reverted on-chain",
            block_number=block_number,
            block_hash=block_hash,
            block_timestamp=block_timestamp,
            actual_fee=actual_fee,
            expected=expected,
        )
        if result["status"] == "failed":
            logger.warning(f"Transaction failed on-chain: {tx_hash}")

    return result


@app.periodic(cron="*/5 * * * *")
@app.task
def check_all_pending_transactions(timestamp: int) -> Dict[str, Any]:
    pending_cutoff = timezone.now() - timedelta(minutes=2)
    pending_txs = Transaction.objects.filter(
        Q(status=TRANSACTION_STATUS_PENDING) | Q(balance_reconciliation_token__isnull=False),
        created_at__lt=pending_cutoff,
    ).select_related("wallet")

    total = pending_txs.count()
    queued = 0

    for tx in pending_txs:
        try:
            confirm_pending_transaction.defer(tx_hash=tx.tx_hash, wallet_uuid=str(tx.wallet.uuid), principal_id=None)
            queued += 1
        except Exception as e:
            logger.error(f"Queue confirmation failed {tx.tx_hash}: {e}")

    if total > 0:
        logger.info(f"Queued {queued}/{total} pending transactions for confirmation")

    return {"total": total, "queued": queued}


@app.task
def cleanup_stale_pending_transactions(timestamp: int) -> Dict[str, Any]:
    stale_cutoff = timezone.now() - timedelta(hours=24)
    overdue = Transaction.objects.filter(
        status=TRANSACTION_STATUS_PENDING,
        created_at__lt=stale_cutoff,
    ).count()

    logger.info("Retained %s overdue wallet transactions for receipt recovery", overdue)
    return {"total": overdue, "failed": 0}
