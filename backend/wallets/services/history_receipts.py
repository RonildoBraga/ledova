from shared.db import atomic
from wallets.constants import (
    TRANSACTION_STATUS_CONFIRMED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_PENDING,
)
from wallets.models import Transaction, Wallet


def record_history_receipt(tx_hash, *, wallet, succeeded, block_number=None, block_timestamp=None, actual_fee=None):
    with atomic():
        Wallet.objects.select_for_update().get(pk=wallet.pk)
        tx = (
            Transaction.objects.select_for_update()
            .filter(tx_hash=tx_hash, wallet=wallet, imported_from_history=True)
            .first()
        )
        if tx is None:
            return {"status": "not_found", "tx_hash": tx_hash}
        if tx.status != TRANSACTION_STATUS_PENDING:
            return {"status": "already_processed", "current_status": tx.status}
        tx.status = TRANSACTION_STATUS_CONFIRMED if succeeded else TRANSACTION_STATUS_FAILED
        if block_number is not None:
            tx.block_number = block_number
        if block_timestamp is not None:
            tx.block_timestamp = block_timestamp
        if actual_fee is not None:
            tx.transaction_fee = actual_fee
        tx.save(update_fields=["status", "block_number", "block_timestamp", "transaction_fee", "updated_at"])
        return {"status": tx.status, "tx_hash": tx_hash, "block_number": tx.block_number}
