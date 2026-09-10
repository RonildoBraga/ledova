import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal
from typing import Any, Callable, Dict, NamedTuple, Optional

from django.db.models import Q
from django.utils import timezone
from procrastinate import RetryStrategy

from integrations.blockchain import get_blockchain_client
from integrations.blockchain.receipts import transaction_hash_matches
from ledova_backend.procrastinate_app import app
from shared.constants import BLOCKCHAIN_BITCOIN, EVM_BLOCKCHAINS
from shared.db import acting_for
from wallets.constants import TRANSACTION_STATUS_PENDING
from wallets.models import Transaction, Wallet
from wallets.services import transaction_confirmation
from wallets.services.history_receipts import record_history_receipt
from wallets.services.receipt_targets import capture_receipt_target

logger = logging.getLogger(__name__)

WEI_TO_ETH = Decimal("1000000000000000000")
SATOSHI_TO_BTC = Decimal("100000000")


def _extract_actual_fee(receipt: Dict[str, Any], chain: str) -> Optional[Decimal]:
    try:
        chain_lower = chain.lower()

        if chain_lower in EVM_BLOCKCHAINS:
            gas_used = receipt.get("gasUsed") or receipt.get("gas_used")
            effective_gas_price = receipt.get("effectiveGasPrice") or receipt.get("effective_gas_price")

            if gas_used is None or effective_gas_price is None:
                return None

            if isinstance(gas_used, str):
                gas_used = int(gas_used, 16) if gas_used.startswith("0x") else int(gas_used)
            if isinstance(effective_gas_price, str):
                effective_gas_price = (
                    int(effective_gas_price, 16) if effective_gas_price.startswith("0x") else int(effective_gas_price)
                )

            fee_wei = Decimal(gas_used) * Decimal(effective_gas_price)
            return fee_wei / WEI_TO_ETH

        elif chain_lower == BLOCKCHAIN_BITCOIN:
            fee = receipt.get("fee")
            if fee is not None:
                return Decimal(fee) / SATOSHI_TO_BTC
            return None

        return None

    except Exception as e:
        logger.warning(f"Failed to extract actual fee: {e}")
        return None


class _ReceiptReader(NamedTuple):

    block_number: Callable[[Dict[str, Any]], Optional[int]]
    succeeded: Callable[[Dict[str, Any]], Optional[bool]]
    block_timestamp: Callable[[Any, Dict[str, Any], Optional[int]], Optional[datetime]]


def _evm_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return receipt.get("blockNumber") or receipt.get("block_number")


def _evm_succeeded(receipt: Dict[str, Any]) -> Optional[bool]:
    status = receipt.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or status not in (0, 1):
        return None
    return status == 1


def _evm_block_timestamp(client: Any, receipt: Dict[str, Any], block_number: Optional[int]) -> Optional[datetime]:
    if not block_number or not hasattr(client, "w3"):
        return None
    try:
        block = client.w3.eth.get_block(block_number)
        if not block:
            return None
        return datetime.fromtimestamp(block["timestamp"], tz=datetime_timezone.utc)
    except Exception:
        return None


def _bitcoin_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return receipt.get("block_height")


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
    block_hash = receipt.get("block_hash")
    if not block_hash or not hasattr(client, "get_block_timestamp"):
        return None
    try:
        seconds = client.get_block_timestamp(block_hash)
    except Exception:
        return None
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, tz=datetime_timezone.utc)


_EVM_RECEIPT_READER = _ReceiptReader(_evm_block_number, _evm_succeeded, _evm_block_timestamp)

_RECEIPT_READERS = {
    BLOCKCHAIN_BITCOIN: _ReceiptReader(_bitcoin_block_number, _bitcoin_succeeded, _bitcoin_block_timestamp),
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
    block_timestamp = reader.block_timestamp(client, receipt, block_number)
    actual_fee = _extract_actual_fee(receipt, wallet.chain)

    if tx.imported_from_history:
        return record_history_receipt(
            tx_hash,
            wallet=wallet,
            succeeded=succeeded,
            block_number=block_number,
            block_timestamp=block_timestamp,
            actual_fee=actual_fee,
            expected=expected,
        )

    if succeeded:
        result = transaction_confirmation.confirm_transaction(
            tx_hash=tx_hash,
            wallet=wallet,
            block_number=block_number,
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
