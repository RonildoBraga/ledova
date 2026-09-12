from shared.db import atomic
from wallets.constants import (
    TRANSACTION_STATUS_CONFIRMED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_PENDING,
)
from wallets.models import Transaction, Wallet
from wallets.services.receipt_metadata import apply_receipt_metadata
from wallets.services.receipt_targets import capture_receipt_target


def record_history_receipt(
    tx_hash,
    *,
    wallet,
    succeeded,
    block_number=None,
    block_hash=None,
    block_timestamp=None,
    actual_fee=None,
    expected=None
):
    with atomic():
        locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        tx = (
            Transaction.objects.select_for_update()
            .filter(tx_hash=tx_hash, wallet=wallet, imported_from_history=True)
            .first()
        )
        if tx is None:
            return {"status": "not_found", "tx_hash": tx_hash}
        if expected is not None and capture_receipt_target(locked_wallet, tx) != expected:
            return {"status": "observation_changed", "tx_hash": tx_hash}
        if tx.status != TRANSACTION_STATUS_PENDING:
            return {"status": "already_processed", "current_status": tx.status}
        tx.status = TRANSACTION_STATUS_CONFIRMED if succeeded else TRANSACTION_STATUS_FAILED
        fields = apply_receipt_metadata(
            tx, block_hash=block_hash, block_number=block_number, block_timestamp=block_timestamp, actual_fee=actual_fee
        )
        tx.save(update_fields=["status", "updated_at", *fields])
        return {"status": tx.status, "tx_hash": tx_hash, "block_number": tx.block_number}
