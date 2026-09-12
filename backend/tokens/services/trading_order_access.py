from rest_framework.exceptions import NotFound

from tokens.exceptions import SwapExpiredException, SwapNotReadyException
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder
from tokens.services.settlement_context import (
    SettlementContextChanged,
    SettlementContextRequired,
    assert_current_settlement,
    recorded_settlement_context,
)
from wallets.models import Wallet


def resolve_order_swap_context(transfer_order, authorized_wallets):
    if (
        transfer_order.wallet_id not in authorized_wallets.wallet_ids
        or transfer_order.wallet.user_account_id != transfer_order.owner_account_id
        or transfer_order.wallet.address.casefold() != transfer_order.wallet_address.casefold()
    ):
        raise NotFound("Order not found.")

    swap_order = SwapOrder.objects.for_transfer_order(transfer_order)
    if not swap_order:
        raise NotFound("No swap order found for this transfer order.")

    if (
        swap_order.sell_order_id == transfer_order.pk
        and swap_order.seller_address.casefold() == transfer_order.wallet_address.casefold()
    ):
        user_role = "seller"
        has_signed = swap_order.seller_has_signed
    elif (
        swap_order.buy_order_id == transfer_order.pk
        and swap_order.buyer_address.casefold() == transfer_order.wallet_address.casefold()
    ):
        user_role = "buyer"
        has_signed = swap_order.buyer_has_signed
    else:
        raise NotFound("Order not found.")

    return swap_order, user_role, has_signed


def resolve_exact_swap_context(user, order_id, identity, snapshot=None):
    order = (
        TransferOrder.objects.visible_to_user(user)
        .filter(pk=order_id, owner_account_id=identity["owner_account_uuid"], wallet_id=identity["wallet_uuid"])
        .first()
    )
    wallet = (
        Wallet.objects.visible_to_user(user)
        .verified_evm()
        .filter(pk=identity["wallet_uuid"], user_account_id=identity["owner_account_uuid"])
        .first()
    )
    if order is None or wallet is None or wallet.address.casefold() != order.wallet_address.casefold():
        raise NotFound("Order not found.")
    swap = SwapOrder.objects.filter(pk=identity["swap_uuid"]).first()
    if swap is None or (snapshot is not None and snapshot.pk != swap.pk):
        raise NotFound("Swap not found.")
    if not swap.settlement_protocol_version:
        raise SettlementContextRequired()
    context = recorded_settlement_context(swap)
    role = next(
        (
            role
            for role in ("seller", "buyer")
            if context[role]["order_uuid"] == str(order.pk)
            and context[role]["owner_account_uuid"] == str(order.owner_account_id)
            and context[role]["wallet_uuid"] == str(wallet.pk)
            and context[role]["payment_asset_uuid"] == (str(order.payment_asset_id) if order.payment_asset_id else None)
            and context[role]["address"].casefold() == wallet.address.casefold()
        ),
        None,
    )
    if role is None or order.token_id != swap.share_token_id:
        raise NotFound("Swap not found.")
    expected_digest = identity.get("settlement_digest")
    if expected_digest is not None and expected_digest != swap.settlement_digest:
        raise SettlementContextChanged()
    return swap, role, swap.seller_has_signed if role == "seller" else swap.buyer_has_signed


def require_pending_settlement(swap):
    if (
        swap.status
        not in (
            SwapOrderStatus.CREATED,
            SwapOrderStatus.SELLER_SIGNED,
            SwapOrderStatus.BUYER_SIGNED,
            SwapOrderStatus.READY,
        )
        or swap.transaction_id is not None
        or swap.tx_hash
    ):
        raise SwapNotReadyException()
    if swap.deadline_passed:
        raise SwapExpiredException()
    return assert_current_settlement(swap)
