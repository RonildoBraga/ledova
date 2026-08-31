import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from assets.models import Asset
from integrations.blockchain import get_blockchain_client
from shared.constants import get_native_asset_symbol, normalize_chain
from shared.utils.logging_utils import LoggingContext
from wallets.constants import (
    SNAPSHOT_REASON_TRANSACTION,
    TRANSACTION_STATUS_CONFIRMED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_PENDING,
)
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet

logger = logging.getLogger("ledova_backend")


class TransactionConfirmationService:

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

        if token_contract:
            asset = Asset.get_by_chain_and_contract(wallet.chain, token_contract)
            if not asset:
                logger.warning(
                    f"{LoggingContext.WALLET_TRANSFER} Token contract not found: {token_contract} "
                    f"on {wallet.chain}, falling back to native asset"
                )
                asset_symbol = get_native_asset_symbol(chain)
                asset, _ = Asset.objects.get_or_create(
                    symbol=asset_symbol,
                    defaults={"name": asset_symbol, "asset_type": "native_crypto"},
                )
        else:
            asset_symbol = get_native_asset_symbol(chain)
            asset, _ = Asset.objects.get_or_create(
                symbol=asset_symbol,
                defaults={"name": asset_symbol, "asset_type": "native_crypto"},
            )

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
                f"{LoggingContext.WALLET_TRANSFER} Created pending transaction: "
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
            logger.warning(f"{LoggingContext.WALLET_SYNC} Transaction not found for confirmation: {tx_hash}")
            return {"status": "not_found", "tx_hash": tx_hash}

        if tx.status == TRANSACTION_STATUS_CONFIRMED:
            logger.info(f"{LoggingContext.WALLET_SYNC} Transaction already confirmed: {tx_hash}")
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

            logger.info(
                f"{LoggingContext.WALLET_SYNC} Transaction confirmed: " f"tx_hash={tx_hash}, block={block_number}"
            )

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
            logger.warning(f"{LoggingContext.WALLET_SYNC} Transaction not found for failure: {tx_hash}")
            return {"status": "not_found", "tx_hash": tx_hash}

        if tx.status != TRANSACTION_STATUS_PENDING:
            logger.info(f"{LoggingContext.WALLET_SYNC} Transaction not pending, cannot fail: {tx_hash}")
            return {"status": "not_pending", "tx_hash": tx_hash, "current_status": tx.status}

        with transaction.atomic():
            tx.status = TRANSACTION_STATUS_FAILED
            tx.save(update_fields=["status"])

            TransactionConfirmationService._revert_optimistic_holding(tx)

            logger.info(
                f"{LoggingContext.WALLET_SYNC} Transaction marked as failed: " f"tx_hash={tx_hash}, reason={reason}"
            )

        return {
            "status": "failed",
            "tx_hash": tx_hash,
            "reason": reason,
        }

    @staticmethod
    def _verify_holding_balance(wallet: Wallet, asset: Asset) -> None:
        try:
            deployment = asset.get_deployment_for_chain(wallet.chain)
            if deployment and deployment.contract_address:
                client = get_blockchain_client(wallet.chain)
                blockchain_balance = client.get_token_balance(
                    address=wallet.address,
                    contract_address=deployment.contract_address,
                    decimals=deployment.decimals,
                )
            elif deployment:
                client = get_blockchain_client(wallet.chain)
                blockchain_balance = client.get_native_balance(wallet.address)
            else:
                return

            if blockchain_balance is None:
                return

            holding = Holding.objects.filter(wallet=wallet, asset=asset).first()
            if holding and holding.quantity != blockchain_balance:
                logger.warning(
                    f"{LoggingContext.WALLET_SYNC} Balance correction: "
                    f"{holding.quantity} -> {blockchain_balance} {asset.symbol}"
                )
                holding.quantity = blockchain_balance
                holding.last_synced_at = timezone.now()
                holding.save(update_fields=["quantity", "last_synced_at"])

        except Exception as e:
            logger.warning(f"{LoggingContext.WALLET_SYNC} Balance verification failed: {e}")

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

        logger.info(
            f"{LoggingContext.WALLET_SYNC} Reverted optimistic holding: "
            f"+{total_reverted} {tx.asset.symbol}, new_balance={holding.quantity}"
        )
