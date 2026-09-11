from blockchain.models import BlockchainTransaction, TransactionType
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder


def lock_orders(queryset):
    return list(queryset.order_by("pk").select_for_update(of=("self",)))


def swap_terms(swap):
    return (
        swap.sell_order_id,
        swap.buy_order_id,
        swap.seller_wallet_id,
        swap.buyer_wallet_id,
        swap.share_token_id,
        swap.payment_asset_id,
        swap.seller_address,
        swap.buyer_address,
        swap.share_amount,
        swap.payment_amount,
        swap.nonce,
        swap.order_hash,
        swap.expires_at,
        swap.expiry_release_eligible,
        swap.settlement_protocol_version,
        swap.settlement_context,
        swap.settlement_digest,
    )


def hash_identity(value):
    if not value:
        return ""
    if isinstance(value, bytes):
        return value.hex()
    return value.lower().removeprefix("0x")


def lock_current_claim(expected_swap, expected_transaction, *, with_orders=False):
    orders = {}
    if with_orders:
        orders = {
            order.pk: order
            for order in lock_orders(
                TransferOrder.objects.filter(pk__in=[expected_swap.sell_order_id, expected_swap.buy_order_id])
            )
        }
    swap = SwapOrder.objects.select_for_update(of=("self",)).filter(pk=expected_swap.pk).first()
    if (
        swap is None
        or expected_swap.status != SwapOrderStatus.EXECUTING
        or swap.status != SwapOrderStatus.EXECUTING
        or swap.transaction_id != expected_transaction.pk
        or expected_swap.transaction_id != expected_transaction.pk
        or swap_terms(swap) != swap_terms(expected_swap)
        or swap.seller_signature != expected_swap.seller_signature
        or swap.buyer_signature != expected_swap.buyer_signature
    ):
        return None
    if with_orders:
        if swap.sell_order_id not in orders or swap.buy_order_id not in orders:
            return None
        swap.sell_order = orders[swap.sell_order_id]
        swap.buy_order = orders[swap.buy_order_id]
    transaction = BlockchainTransaction.objects.select_for_update(of=("self",)).get(pk=swap.transaction_id)
    if (
        transaction.tx_type != TransactionType.ATOMIC_SWAP
        or transaction.related_model != "tokens.SwapOrder"
        or transaction.related_uuid != swap.pk
        or transaction.function_name != "executeSwap"
        or hash_identity(swap.tx_hash) != hash_identity(expected_swap.tx_hash)
        or hash_identity(transaction.tx_hash) != hash_identity(expected_transaction.tx_hash)
        or hash_identity(swap.tx_hash) != hash_identity(transaction.tx_hash)
    ):
        return None
    if swap.settlement_protocol_version:
        from tokens.services.settlement_context import (
            recorded_settlement_context,
            settlement_execution_arguments,
        )

        context = recorded_settlement_context(swap)
        if (
            transaction.function_args != settlement_execution_arguments(swap)
            or expected_transaction.function_args != transaction.function_args
            or transaction.to_address != context["typed_data"]["domain"]["verifyingContract"]
            or expected_transaction.to_address != transaction.to_address
        ):
            return None
    return swap, transaction
