from rest_framework.exceptions import NotFound

from tokens.models import SwapOrder


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
