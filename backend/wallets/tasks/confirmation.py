import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

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

    block_number = receipt.get("blockNumber") or receipt.get("block_number")
    block_timestamp = None
    actual_fee = _extract_actual_fee(receipt, wallet.chain)

    if block_number:
        try:
            block = client.w3.eth.get_block(block_number) if hasattr(client, "w3") else None
            if block:
                block_timestamp = timezone.datetime.fromtimestamp(block["timestamp"], tz=timezone.utc)
        except Exception:
            block_timestamp = timezone.now()

    tx_status = receipt.get("status", 1)
    if tx_status == 1 or tx_status is True:
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
    """Queue a confirmation job for every pending transaction older than 2 min."""
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
    """Mark pending transactions older than 24h as failed."""
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
