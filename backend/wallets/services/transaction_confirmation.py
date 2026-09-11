import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import uuid4

from django.utils import timezone

from assets.models import Asset, AssetType
from assets.services.identity import (
    native_asset_for_chain,
    recorded_native_asset_for_chain,
)
from compliance.services.transaction_monitoring import TransactionMonitoringService
from shared.constants import get_native_asset_symbol, normalize_chain
from shared.db import atomic
from users.services.accounts import account_members
from users.tasks.notifications import send_transaction_notification
from wallets.constants import (
    SNAPSHOT_REASON_TRANSACTION,
    TRANSACTION_STATUS_CONFIRMED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_PENDING,
    TRANSACTION_STATUS_REORGED,
    TRANSACTION_STATUS_REPLACED,
    TRANSACTION_STATUSES_THAT_RETURN_THE_OPTIMISTIC_DEBIT,
)
from wallets.exceptions import InvalidTransactionException
from wallets.models import (
    Holding,
    HoldingSnapshot,
    Transaction,
    Wallet,
    WalletSubmission,
)
from wallets.services.holdings import sync_holding
from wallets.services.receipt_metadata import apply_receipt_metadata
from wallets.services.receipt_targets import capture_receipt_target

logger = logging.getLogger(__name__)

NOT_TRANSFERABLE = "{symbol} is a tokenized security. Shares move by allotment, not by a wallet transfer."


def resolve_transfer_asset(wallet: Wallet, token_contract: Optional[str] = None) -> Asset:
    if not token_contract:
        return native_asset_for_chain(wallet.chain)

    asset = Asset.get_by_chain_and_contract(wallet.chain, token_contract)
    if asset is None or not asset.is_verified:
        raise InvalidTransactionException(
            f"Token contract {token_contract} is not a verified asset on {normalize_chain(wallet.chain)}."
        )
    if asset.asset_type == AssetType.TOKENIZED_SECURITY.value:
        raise InvalidTransactionException(NOT_TRANSFERABLE.format(symbol=asset.symbol))
    return asset


def create_pending_transaction(
    wallet: Wallet,
    tx_hash: str,
    to_address: str,
    amount: Decimal,
    transaction_fee: Optional[Decimal] = None,
    token_contract: Optional[str] = None,
) -> Dict[str, Any]:
    chain = normalize_chain(wallet.chain)
    asset = resolve_transfer_asset(wallet, token_contract)

    with atomic():
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
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

        fee = transaction_fee or Decimal("0")
        native = native_asset_for_chain(wallet.chain)

        if asset == native:
            holding, taken = _move_holding(tx, asset, -(amount + fee))
            tx.deducted_amount = -taken
            tx.deducted_amount_sync_version = holding.sync_version
        else:
            holding, taken = _move_holding(tx, asset, -amount)
            tx.deducted_amount = -taken
            tx.deducted_amount_sync_version = holding.sync_version
            if fee:
                native_holding, taken_fee = _move_holding(tx, native, -fee)
                tx.deducted_fee = -taken_fee
                tx.deducted_fee_sync_version = native_holding.sync_version
        tx.save(
            update_fields=[
                "deducted_amount",
                "deducted_fee",
                "deducted_amount_sync_version",
                "deducted_fee_sync_version",
            ]
        )

        logger.info(
            "Created pending transaction: "
            f"tx_hash={tx_hash}, wallet={wallet.address[:10]}..., "
            f"amount={amount} {asset.symbol}, fee={fee} {native.symbol}, new_balance={holding.quantity}"
        )

    return {
        "transaction_id": str(tx.uuid),
        "tx_hash": tx_hash,
        "status": TRANSACTION_STATUS_PENDING,
        "holding_quantity": str(holding.quantity),
    }


def confirm_transaction(
    tx_hash: str,
    *,
    wallet: Wallet,
    block_number: Optional[int] = None,
    block_hash: Optional[str] = None,
    block_timestamp: Optional[timezone.datetime] = None,
    actual_fee: Optional[Decimal] = None,
    expected=None,
) -> Dict[str, Any]:
    if WalletSubmission.objects.filter(wallet=wallet, tx_hash=tx_hash).exists():
        return _observe_family_transaction(wallet, tx_hash)

    def confirm_once(tx):
        if tx.status == TRANSACTION_STATUS_CONFIRMED:
            return {"status": "already_confirmed", "tx_hash": tx_hash}, None
        tx.status = TRANSACTION_STATUS_CONFIRMED
        fields = apply_receipt_metadata(
            tx, block_hash=block_hash, block_number=block_number, block_timestamp=block_timestamp, actual_fee=actual_fee
        )
        tx.balance_reconciliation_token = uuid4()
        tx.save(update_fields=["status", "balance_reconciliation_token", *fields])
        _invalidate_balance_reads(tx)

        _notify_wallet_users(tx, "confirmed")
        logger.info(f"Transaction confirmed: tx_hash={tx_hash}, block={block_number}")
        return {"status": "confirmed", "tx_hash": tx_hash, "block_number": block_number}, None

    result = _on_this_wallets_row(tx_hash, wallet, confirm_once, expected=expected)
    if result["status"] == "observation_changed":
        return result
    reconcile_transaction(tx_hash, wallet=wallet)
    return result


def fail_transaction(
    tx_hash: str,
    reason: Optional[str] = None,
    *,
    wallet: Wallet,
    block_number: Optional[int] = None,
    block_hash: Optional[str] = None,
    block_timestamp: Optional[timezone.datetime] = None,
    actual_fee: Optional[Decimal] = None,
    expected=None,
) -> Dict[str, Any]:
    if WalletSubmission.objects.filter(wallet=wallet, tx_hash=tx_hash).exists():
        return _observe_family_transaction(wallet, tx_hash)

    def fail_once(tx):
        if tx.status != TRANSACTION_STATUS_PENDING:
            return {"status": "not_pending", "tx_hash": tx_hash, "current_status": tx.status}, None
        fields = apply_receipt_metadata(
            tx, block_hash=block_hash, block_number=block_number, block_timestamp=block_timestamp, actual_fee=actual_fee
        )
        _settle_the_optimistic_debit(tx, TRANSACTION_STATUS_FAILED, fields)
        _notify_wallet_users(tx, "failed")
        logger.info(f"Transaction marked as failed: tx_hash={tx_hash}, reason={reason}")
        return {"status": "failed", "tx_hash": tx_hash, "reason": reason}, None

    result = _on_this_wallets_row(tx_hash, wallet, fail_once, expected=expected)
    if result["status"] == "observation_changed":
        return result
    reconcile_transaction(tx_hash, wallet=wallet)
    return result


def mark_reorged(tx_hash: str, wallet: Wallet) -> Dict[str, Any]:
    if WalletSubmission.objects.filter(wallet=wallet, tx_hash=tx_hash).exists():
        return _observe_family_transaction(wallet, tx_hash)

    def reverse_once(tx):
        if tx.status != TRANSACTION_STATUS_CONFIRMED:
            return {"status": "not_confirmed", "tx_hash": tx_hash, "current_status": tx.status}, None

        _settle_the_optimistic_debit(tx, TRANSACTION_STATUS_REORGED)
        _notify_wallet_users(tx, "reorged")
        logger.warning(f"Transaction dropped by a reorganisation: tx_hash={tx_hash}, block={tx.block_number}")
        return {"status": TRANSACTION_STATUS_REORGED, "tx_hash": tx_hash}, None

    result = _on_this_wallets_row(tx_hash, wallet, reverse_once)
    reconcile_transaction(tx_hash, wallet=wallet)
    return result


def mark_replaced(tx_hash: str, wallet: Wallet, replacement_tx_hash: str) -> Dict[str, Any]:
    if WalletSubmission.objects.filter(wallet=wallet, tx_hash=tx_hash).exists():
        return _observe_family_transaction(wallet, tx_hash)

    def link_and_leave_the_holding(tx):
        if tx.status != TRANSACTION_STATUS_PENDING:
            return {"status": "not_pending", "tx_hash": tx_hash, "current_status": tx.status}, None

        tx.replaced_by_tx_hash = replacement_tx_hash
        _settle_the_optimistic_debit(tx, TRANSACTION_STATUS_REPLACED, ["replaced_by_tx_hash"])
        _notify_wallet_users(tx, "replaced")
        logger.info(f"Transaction replaced: tx_hash={tx_hash} landed as {replacement_tx_hash}")
        return {
            "status": TRANSACTION_STATUS_REPLACED,
            "tx_hash": tx_hash,
            "replaced_by": replacement_tx_hash,
        }, None

    return _on_this_wallets_row(tx_hash, wallet, link_and_leave_the_holding)


def _settle_the_optimistic_debit(tx: Transaction, status: str, extra_fields=None) -> None:
    tx.status = status
    fields = ["status", "updated_at", *(extra_fields or [])]
    if status in TRANSACTION_STATUSES_THAT_RETURN_THE_OPTIMISTIC_DEBIT:
        tx.balance_reconciliation_token = uuid4()
        fields.append("balance_reconciliation_token")
    tx.save(update_fields=fields)
    if status in TRANSACTION_STATUSES_THAT_RETURN_THE_OPTIMISTIC_DEBIT:
        _invalidate_balance_reads(tx)
        _revert_optimistic_holding(tx, clear_superseded=status != TRANSACTION_STATUS_REORGED)


def _invalidate_balance_reads(tx: Transaction) -> None:
    native = recorded_native_asset_for_chain(tx.wallet.chain)
    Holding.objects.filter(wallet=tx.wallet, asset__in=[tx.asset, native]).update(balance_version=uuid4())


def reconcile_transaction(tx_hash: str, *, wallet: Wallet) -> bool:
    if WalletSubmission.objects.filter(wallet=wallet, tx_hash=tx_hash).exists():
        _observe_family_transaction(wallet, tx_hash)
        return not Transaction.objects.filter(
            wallet=wallet, tx_hash=tx_hash, balance_reconciliation_token__isnull=False
        ).exists()

    tx = Transaction.objects.select_related("asset").filter(tx_hash=tx_hash, wallet=wallet).first()
    if tx is None or tx.balance_reconciliation_token is None:
        return True
    expected = tx.balance_reconciliation_token
    if not _verify_holding_balance(wallet, tx.asset):
        return False
    with atomic():
        Wallet.objects.select_for_update().get(pk=wallet.pk)
        locked = Transaction.objects.select_for_update().get(pk=tx.pk)
        if locked.balance_reconciliation_token != expected:
            return False
        if locked.status == TRANSACTION_STATUS_CONFIRMED:
            _update_snapshot_on_confirmation(locked)
        if locked.status == TRANSACTION_STATUS_REORGED:
            locked.deducted_amount = Decimal("0")
            locked.deducted_fee = Decimal("0")
        locked.balance_reconciliation_token = None
        locked.save(update_fields=["balance_reconciliation_token", "deducted_amount", "deducted_fee"])
    return True


def _on_this_wallets_row(tx_hash: str, wallet: Wallet, act, *, expected=None) -> Dict[str, Any]:
    with atomic():
        locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        tx = Transaction.objects.select_for_update().filter(tx_hash=tx_hash, wallet=wallet).first()
        if tx is None:
            return {"status": "not_found", "tx_hash": tx_hash}
        if expected is not None and capture_receipt_target(locked_wallet, tx) != expected:
            return {"status": "observation_changed", "tx_hash": tx_hash}
        answer, refusal = act(tx)

    if refusal is not None:
        raise refusal
    return answer


def _notify_wallet_users(tx: Transaction, event: str) -> None:
    for user in account_members(tx.wallet.user_account):
        send_transaction_notification.defer(user_id=str(user.pk), transaction_id=str(tx.uuid), event_type=event)


def _move_holding(tx: Transaction, asset: Asset, delta: Decimal) -> tuple[Holding, Decimal]:
    holding, _ = Holding.objects.select_for_update().get_or_create(
        wallet=tx.wallet,
        asset=asset,
        defaults={"quantity": Decimal("0")},
    )

    before = holding.quantity
    holding.quantity = max(Decimal("0"), before + delta)
    holding.balance_version = uuid4()
    holding.save(update_fields=["quantity", "balance_version", "updated_at"])

    HoldingSnapshot.objects.update_or_create(
        holding=holding,
        snapshot_date=timezone.now().date(),
        defaults={
            "quantity": holding.quantity,
            "snapshot_reason": SNAPSHOT_REASON_TRANSACTION,
            "caused_by_transaction": tx,
        },
    )
    return holding, holding.quantity - before


def _verify_holding_balance(wallet: Wallet, asset: Asset) -> bool:
    holding = sync_holding(wallet, asset)
    native = recorded_native_asset_for_chain(wallet.chain)
    if native is None:
        return False
    if asset != native:
        native_holding = sync_holding(wallet, native)
        return holding is not None and native_holding is not None
    return holding is not None


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


def _revert_optimistic_holding(tx: Transaction, *, clear_superseded=True) -> None:
    with atomic():
        Wallet.objects.select_for_update().get(pk=tx.wallet_id)
        locked = Transaction.objects.select_for_update().get(pk=tx.pk)
        _return_outstanding_deductions(locked, clear_superseded=clear_superseded)
        tx.deducted_amount = locked.deducted_amount
        tx.deducted_fee = locked.deducted_fee


def _return_outstanding_deductions(tx: Transaction, *, clear_superseded=True) -> None:
    native = recorded_native_asset_for_chain(tx.wallet.chain)
    amount, fee = _deductions_to_reverse(tx, native)
    if clear_superseded or amount:
        tx.deducted_amount = Decimal("0")
    if native is not None and (clear_superseded or fee):
        tx.deducted_fee = Decimal("0")
    tx.save(update_fields=["deducted_amount", "deducted_fee"])
    if not amount and not fee:
        return
    holding, _ = _move_holding(tx, tx.asset, amount)
    if fee:
        _move_holding(tx, native, fee)

    logger.info(
        f"Reverted optimistic holding: +{amount} {tx.asset.symbol} "
        f"and +{fee} {get_native_asset_symbol(tx.wallet.chain)}, "
        f"new_balance={holding.quantity}"
    )


def _deductions_to_reverse(tx: Transaction, native: Asset) -> tuple[Decimal, Decimal]:
    return (
        _outstanding_deduction(tx, tx.asset, tx.deducted_amount, tx.deducted_amount_sync_version),
        _outstanding_deduction(tx, native, tx.deducted_fee, tx.deducted_fee_sync_version),
    )


def _outstanding_deduction(tx, asset, amount, sync_version) -> Decimal:
    if amount is None or sync_version is None:
        return Decimal("0")
    holding = (
        Holding.objects.select_for_update().filter(wallet=tx.wallet, asset=asset, sync_version=sync_version).first()
    )
    return amount if holding is not None else Decimal("0")


def _observe_family_transaction(wallet, tx_hash):
    from wallets.services.chain_observations import observe_wallet_chain

    tx = Transaction.objects.get(wallet=wallet, tx_hash=tx_hash)
    outcome = observe_wallet_chain(tx.pk, reconcile=True)
    tx.refresh_from_db()
    return {"status": tx.status, "tx_hash": tx_hash, "observation": outcome}
