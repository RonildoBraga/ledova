import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal, localcontext
from typing import Any, Callable, Dict, NamedTuple, Optional

from django.db.models import Q
from django.utils import timezone
from procrastinate import RetryStrategy

from integrations.blockchain import get_blockchain_client
from integrations.blockchain.receipts import (
    nonnegative_integer,
    normalized_hash,
    transaction_hash_matches,
)
from ledova_backend.procrastinate_app import app
from shared.constants import BLOCKCHAIN_BITCOIN, EVM_BLOCKCHAINS
from shared.db import acting_for
from wallets.constants import TRANSACTION_STATUS_PENDING
from wallets.models import Transaction, Wallet
from wallets.services import transaction_confirmation
from wallets.services.history_receipts import record_history_receipt
from wallets.services.receipt_targets import capture_receipt_target

logger = logging.getLogger(__name__)

MAX_BLOCK_NUMBER = 2**63 - 1
MAX_EVM_QUANTITY = 2**256 - 1


def _receipt_field(receipt, primary, alias):
    return receipt.get(primary) if primary in receipt else receipt.get(alias)


def _extract_actual_fee(receipt: Dict[str, Any], chain: str) -> Optional[Decimal]:
    if chain.lower() in EVM_BLOCKCHAINS:
        gas_used = nonnegative_integer(
            _receipt_field(receipt, "gasUsed", "gas_used"), maximum=MAX_EVM_QUANTITY, encoded=True
        )
        gas_price = nonnegative_integer(
            _receipt_field(receipt, "effectiveGasPrice", "effective_gas_price"),
            maximum=MAX_EVM_QUANTITY,
            encoded=True,
        )
        if gas_used is None or gas_price is None:
            return None
        raw_fee, decimals = gas_used * gas_price, 18
    elif chain.lower() == BLOCKCHAIN_BITCOIN:
        raw_fee, decimals = nonnegative_integer(receipt.get("fee"), maximum=10**20 - 1), 8
    else:
        return None
    if raw_fee is None or raw_fee >= 10 ** (12 + decimals):
        return None
    with localcontext() as context:
        context.prec = 30
        return Decimal(raw_fee).scaleb(-decimals)


class _ReceiptReader(NamedTuple):

    block_number: Callable[[Dict[str, Any]], Optional[int]]
    succeeded: Callable[[Dict[str, Any]], Optional[bool]]
    block_timestamp: Callable[[Any, Dict[str, Any], Optional[int]], Optional[datetime]]
    block_hash: Callable[[Dict[str, Any]], Optional[str]]


def _evm_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return nonnegative_integer(
        _receipt_field(receipt, "blockNumber", "block_number"), maximum=MAX_BLOCK_NUMBER, encoded=True
    )


def _evm_block_hash(receipt):
    value = normalized_hash(_receipt_field(receipt, "blockHash", "block_hash"))
    return "0x" + value if value is not None else None


def _block_time(seconds, *, encoded=False):
    seconds = nonnegative_integer(seconds, maximum=253402300799, encoded=encoded)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=datetime_timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _evm_succeeded(receipt: Dict[str, Any]) -> Optional[bool]:
    status = receipt.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or status not in (0, 1):
        return None
    return status == 1


def _evm_block_timestamp(client: Any, receipt: Dict[str, Any], block_number: Optional[int]) -> Optional[datetime]:
    block_hash = _evm_block_hash(receipt)
    if block_hash is None or block_number is None or not hasattr(client, "w3"):
        return None
    try:
        block = client.w3.eth.get_block(block_hash)
        if (
            not isinstance(block, Mapping)
            or not transaction_hash_matches(block.get("hash"), block_hash)
            or nonnegative_integer(block.get("number"), maximum=MAX_BLOCK_NUMBER, encoded=True) != block_number
        ):
            return None
        return _block_time(block.get("timestamp"), encoded=True)
    except Exception:
        return None


def _bitcoin_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return nonnegative_integer(receipt.get("block_height"), maximum=MAX_BLOCK_NUMBER)


def _bitcoin_block_hash(receipt):
    return normalized_hash(receipt.get("block_hash"))


def _bitcoin_succeeded(receipt: Dict[str, Any]) -> Optional[bool]:
    confirmations = receipt.get("confirmations")
    if (
        receipt.get("confirmed") is True
        and isinstance(confirmations, int)
        and not isinstance(confirmations, bool)
        and confirmations > 0
    ):
        return True
    return None


def _bitcoin_block_timestamp(client: Any, receipt: Dict[str, Any], block_number: Optional[int]) -> Optional[datetime]:
    block_hash = _bitcoin_block_hash(receipt)
    if block_hash is None or block_number is None or not hasattr(client, "get_block_timestamp"):
        return None
    try:
        seconds = client.get_block_timestamp(block_hash, expected_height=block_number)
    except Exception:
        return None
    return _block_time(seconds)


_EVM_RECEIPT_READER = _ReceiptReader(_evm_block_number, _evm_succeeded, _evm_block_timestamp, _evm_block_hash)

_RECEIPT_READERS = {
    BLOCKCHAIN_BITCOIN: _ReceiptReader(
        _bitcoin_block_number, _bitcoin_succeeded, _bitcoin_block_timestamp, _bitcoin_block_hash
    ),
}


def get_receipt_reader(chain: str) -> _ReceiptReader:
    return _RECEIPT_READERS.get(chain.lower(), _EVM_RECEIPT_READER)


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
    actual_fee = _extract_actual_fee(receipt, wallet.chain)

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
