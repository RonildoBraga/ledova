import logging
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal
from typing import Any, Callable, Dict, NamedTuple, Optional

from django.utils import timezone
from procrastinate import RetryStrategy

from integrations.blockchain import get_blockchain_client
from ledova_backend.procrastinate_app import app
from shared.constants import BLOCKCHAIN_BITCOIN, EVM_BLOCKCHAINS
from wallets.constants import TRANSACTION_STATUS_PENDING
from wallets.models import Transaction, Wallet
from wallets.services.transaction_confirmation import TransactionConfirmationService

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
    succeeded: Callable[[Dict[str, Any]], bool]
    block_timestamp: Callable[[Any, Dict[str, Any], Optional[int]], Optional[datetime]]


def _evm_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return receipt.get("blockNumber") or receipt.get("block_number")


def _evm_succeeded(receipt: Dict[str, Any]) -> bool:
    status = receipt.get("status", 1)
    return status == 1 or status is True


def _evm_block_timestamp(client: Any, receipt: Dict[str, Any], block_number: Optional[int]) -> Optional[datetime]:
    if not block_number or not hasattr(client, "w3"):
        return None
    try:
        block = client.w3.eth.get_block(block_number)
    except Exception:
        return timezone.now()
    if not block:
        return None
    return datetime.fromtimestamp(block["timestamp"], tz=datetime_timezone.utc)


def _bitcoin_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return receipt.get("block_height")


def _bitcoin_succeeded(receipt: Dict[str, Any]) -> bool:
    return bool(receipt.get("confirmed")) and int(receipt.get("confirmations") or 0) > 0


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
def confirm_pending_transaction(tx_hash: str, wallet_uuid: str) -> Dict[str, Any]:
    try:
        wallet = Wallet.objects.get(uuid=wallet_uuid)
    except Wallet.DoesNotExist:
        logger.error(f"Wallet not found: {wallet_uuid}")
        return {"status": "error", "error": "Wallet not found"}

    try:
        tx = Transaction.objects.get(tx_hash=tx_hash, wallet=wallet)
        if tx.status != TRANSACTION_STATUS_PENDING:
            logger.info(f"Transaction already processed: {tx_hash}")
            return {"status": "already_processed", "current_status": tx.status}
    except Transaction.DoesNotExist:
        pass

    client = get_blockchain_client(wallet.chain)
    receipt = client.get_transaction_receipt(tx_hash)

    if receipt is None:
        logger.info(f"Transaction not yet confirmed: {tx_hash}")
        raise RuntimeError(f"receipt not yet available for {tx_hash}")

    reader = get_receipt_reader(wallet.chain)
    block_number = reader.block_number(receipt)
    block_timestamp = reader.block_timestamp(client, receipt, block_number)
    actual_fee = _extract_actual_fee(receipt, wallet.chain)

    if reader.succeeded(receipt):
        result = TransactionConfirmationService.confirm_transaction(
            tx_hash=tx_hash,
            block_number=block_number,
            block_timestamp=block_timestamp,
            actual_fee=actual_fee,
        )
        logger.info(f"Transaction confirmed: {tx_hash}, actual_fee={actual_fee}")
    else:
        result = TransactionConfirmationService.fail_transaction(
            tx_hash=tx_hash,
            reason="Transaction reverted on-chain",
        )
        logger.warning(f"Transaction failed on-chain: {tx_hash}")

    return result


@app.periodic(cron="*/5 * * * *")
@app.task
def check_all_pending_transactions(timestamp: int) -> Dict[str, Any]:
    pending_cutoff = timezone.now() - timedelta(minutes=2)
    pending_txs = Transaction.objects.filter(
        status=TRANSACTION_STATUS_PENDING,
        created_at__lt=pending_cutoff,
    ).select_related("wallet")

    total = pending_txs.count()
    queued = 0

    for tx in pending_txs:
        try:
            confirm_pending_transaction.defer(tx_hash=tx.tx_hash, wallet_uuid=str(tx.wallet.uuid))
            queued += 1
        except Exception as e:
            logger.error(f"Queue confirmation failed {tx.tx_hash}: {e}")

    if total > 0:
        logger.info(f"Queued {queued}/{total} pending transactions for confirmation")

    return {"total": total, "queued": queued}


@app.periodic(cron="0 3 * * *")
@app.task
def cleanup_stale_pending_transactions(timestamp: int) -> Dict[str, Any]:
    stale_cutoff = timezone.now() - timedelta(hours=24)
    stale_txs = Transaction.objects.filter(
        status=TRANSACTION_STATUS_PENDING,
        created_at__lt=stale_cutoff,
    ).select_related("wallet")

    total = stale_txs.count()
    failed = 0

    for tx in stale_txs:
        try:
            result = TransactionConfirmationService.fail_transaction(
                tx_hash=tx.tx_hash,
                reason="Transaction stale - not confirmed within 24 hours",
            )
            if result["status"] == "failed":
                failed += 1
        except Exception as e:
            logger.error(f"Stale cleanup failed {tx.tx_hash}: {e}")

    if total > 0:
        logger.info(f"Marked {failed}/{total} stale transactions as failed")

    return {"total": total, "failed": failed}
