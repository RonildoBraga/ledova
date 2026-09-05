import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from assets.models import Asset
from assets.services.identity import native_asset_for_chain
from compliance.services.transaction_monitoring import TransactionMonitoringService
from shared.constants import normalize_chain
from users.tasks.notifications import send_transaction_notification
from wallets.constants import (
    SNAPSHOT_REASON_TRANSACTION,
    TRANSACTION_STATUS_CONFIRMED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_PENDING,
)
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet
from wallets.services.chain import fetch_chain_balance

logger = logging.getLogger(__name__)


class TransactionConfirmationService:

    @staticmethod
    def resolve_transfer_asset(wallet: Wallet, token_contract: Optional[str] = None) -> Asset:
        if not token_contract:
            return native_asset_for_chain(wallet.chain)

        asset = Asset.get_by_chain_and_contract(wallet.chain, token_contract)
        if asset is None or not asset.is_verified:
            raise InvalidTransactionException(
                f"Token contract {token_contract} is not a verified asset on {normalize_chain(wallet.chain)}."
            )
        return asset

    @staticmethod
    def create_pending_transaction(
        wallet: Wallet,
        tx_hash: str,
        to_address: str,
        amount: Decimal,
        transaction_fee: Optional[Decimal] = None,
        token_contract: Optional[str] = None,
    ) -> Dict[str, Any]:
        chain = normalize_chain(wallet.chain)
        asset = TransactionConfirmationService.resolve_transfer_asset(wallet, token_contract)

        with transaction.atomic():
            tx = Transaction.objects.create(
                wallet=wallet,
                tx_hash=tx_hash,
                chain=chain,
                from_address=wallet.address,
                to_address=to_address,
                asset=asset,
                amount=amount,
                transaction_fee_estimated=transaction_fee,
                transaction_fee=None,
                status=TRANSACTION_STATUS_PENDING,
                block_timestamp=None,
                block_number=None,
            )
            TransactionMonitoringService.check_new_transaction(tx)

            holding, _ = Holding.objects.get_or_create(
                wallet=wallet,
                asset=asset,
                defaults={"quantity": Decimal("0")},
            )

            total_deduction = amount + (transaction_fee or Decimal("0"))
            new_quantity = holding.quantity - total_deduction
            holding.quantity = max(Decimal("0"), new_quantity)
            holding.last_synced_at = timezone.now()
            holding.save(update_fields=["quantity", "last_synced_at"])

            HoldingSnapshot.objects.update_or_create(
                holding=holding,
                snapshot_date=timezone.now().date(),
                defaults={
                    "quantity": holding.quantity,
                    "snapshot_reason": SNAPSHOT_REASON_TRANSACTION,
                    "caused_by_transaction": tx,
                },
            )

            logger.info(
                "Created pending transaction: "
                f"tx_hash={tx_hash}, wallet={wallet.address[:10]}..., "
                f"amount={amount} {asset.symbol}, new_balance={holding.quantity}"
            )

        return {
            "transaction_id": str(tx.uuid),
            "tx_hash": tx_hash,
            "status": TRANSACTION_STATUS_PENDING,
            "holding_quantity": str(holding.quantity),
        }

    @staticmethod
    def confirm_transaction(
        tx_hash: str,
        block_number: Optional[int] = None,
        block_timestamp: Optional[timezone.datetime] = None,
        actual_fee: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        try:
            tx = Transaction.objects.select_related("wallet", "asset").get(tx_hash=tx_hash)
        except Transaction.DoesNotExist:
            logger.warning(f"Transaction not found for confirmation: {tx_hash}")
            return {"status": "not_found", "tx_hash": tx_hash}

        if tx.status == TRANSACTION_STATUS_CONFIRMED:
            logger.info(f"Transaction already confirmed: {tx_hash}")
            return {"status": "already_confirmed", "tx_hash": tx_hash}

        with transaction.atomic():
            tx.status = TRANSACTION_STATUS_CONFIRMED
            tx.block_number = block_number
            tx.block_timestamp = block_timestamp or timezone.now()
            if actual_fee is not None:
                tx.transaction_fee = actual_fee
            tx.save(update_fields=["status", "block_number", "block_timestamp", "transaction_fee"])

            TransactionConfirmationService._verify_holding_balance(tx.wallet, tx.asset)

            TransactionConfirmationService._update_snapshot_on_confirmation(tx)
            TransactionConfirmationService._notify_wallet_users(tx, "confirmed")

            logger.info(f"Transaction confirmed: tx_hash={tx_hash}, block={block_number}")

        return {
            "status": "confirmed",
            "tx_hash": tx_hash,
            "block_number": block_number,
        }

    @staticmethod
    def fail_transaction(tx_hash: str, reason: Optional[str] = None) -> Dict[str, Any]:
        try:
            tx = Transaction.objects.select_related("wallet", "asset").get(tx_hash=tx_hash)
        except Transaction.DoesNotExist:
            logger.warning(f"Transaction not found for failure: {tx_hash}")
            return {"status": "not_found", "tx_hash": tx_hash}

        if tx.status != TRANSACTION_STATUS_PENDING:
            logger.info(f"Transaction not pending, cannot fail: {tx_hash}")
            return {"status": "not_pending", "tx_hash": tx_hash, "current_status": tx.status}

        with transaction.atomic():
            tx.status = TRANSACTION_STATUS_FAILED
            tx.save(update_fields=["status"])

            TransactionConfirmationService._revert_optimistic_holding(tx)
            TransactionConfirmationService._notify_wallet_users(tx, "failed")

            logger.info(f"Transaction marked as failed: tx_hash={tx_hash}, reason={reason}")

        return {
            "status": "failed",
            "tx_hash": tx_hash,
            "reason": reason,
        }

    @staticmethod
    def _notify_wallet_users(tx: Transaction, event: str) -> None:
        recipients = get_user_model().objects.filter(userprofile__user_accounts__wallets=tx.wallet).distinct()
        for user in recipients:
            send_transaction_notification.defer(user_id=str(user.pk), transaction_id=str(tx.uuid), event_type=event)

    @staticmethod
    def _verify_holding_balance(wallet: Wallet, asset: Asset) -> None:
        blockchain_balance = fetch_chain_balance(wallet, asset)
        if blockchain_balance is None:
            return

        holding = Holding.objects.filter(wallet=wallet, asset=asset).first()
        if holding and holding.quantity != blockchain_balance:
            logger.warning(f"Balance correction: {holding.quantity} -> {blockchain_balance} {asset.symbol}")
            holding.quantity = blockchain_balance
            holding.last_synced_at = timezone.now()
            holding.save(update_fields=["quantity", "last_synced_at"])

    @staticmethod
    def _update_snapshot_on_confirmation(tx: Transaction) -> None:
        if not tx.block_timestamp:
            return

        snapshot_date = tx.block_timestamp.date()
        holding = Holding.objects.filter(wallet=tx.wallet, asset=tx.asset).first()

        if not holding:
            return

        HoldingSnapshot.objects.update_or_create(
            holding=holding,
            snapshot_date=snapshot_date,
            defaults={
                "quantity": holding.quantity,
                "block_number": tx.block_number,
                "snapshot_reason": SNAPSHOT_REASON_TRANSACTION,
                "caused_by_transaction": tx,
            },
        )

    @staticmethod
    def _revert_optimistic_holding(tx: Transaction) -> None:
        holding = Holding.objects.filter(wallet=tx.wallet, asset=tx.asset).first()
        if not holding:
            return

        total_reverted = tx.amount + (tx.transaction_fee or Decimal("0"))
        holding.quantity += total_reverted
        holding.last_synced_at = timezone.now()
        holding.save(update_fields=["quantity", "last_synced_at"])

        HoldingSnapshot.objects.update_or_create(
            holding=holding,
            snapshot_date=timezone.now().date(),
            defaults={
                "quantity": holding.quantity,
                "snapshot_reason": SNAPSHOT_REASON_TRANSACTION,
                "caused_by_transaction": tx,
            },
        )

        logger.info(f"Reverted optimistic holding: +{total_reverted} {tx.asset.symbol}, new_balance={holding.quantity}")
