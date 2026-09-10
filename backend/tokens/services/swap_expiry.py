from django.db.models import Q
from django.utils import timezone

from blockchain.models import BlockchainTransaction
from shared.db import atomic
from tokens.events import publish_trading_event
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder, TransferOrderStatus
from tokens.services.trading_locks import lock_orders, swap_terms

UNCLAIMED_STATES = {
    SwapOrderStatus.CREATED: (False, False),
    SwapOrderStatus.SELLER_SIGNED: (True, False),
    SwapOrderStatus.BUYER_SIGNED: (False, True),
    SwapOrderStatus.READY: (True, True),
}
ACTIVE_STATES = (*UNCLAIMED_STATES, SwapOrderStatus.EXECUTING)


@atomic(durable=True)
def expire_unclaimed_swap(snapshot, cutoff):
    orders = {
        order.pk: order
        for order in lock_orders(TransferOrder.objects.filter(pk__in=[snapshot.sell_order_id, snapshot.buy_order_id]))
    }
    swap = SwapOrder.objects.select_for_update(of=("self",)).filter(pk=snapshot.pk).first()
    if (
        swap is None
        or not swap.expiry_release_eligible
        or swap_terms(swap) != swap_terms(snapshot)
        or swap.expires_at >= cutoff
        or swap.status not in UNCLAIMED_STATES
        or (bool(swap.seller_signature), bool(swap.buyer_signature)) != UNCLAIMED_STATES[swap.status]
        or swap.transaction_id is not None
        or swap.tx_hash
        or len(orders) != 2
    ):
        return False
    if BlockchainTransaction.objects.filter(related_model="tokens.SwapOrder", related_uuid=swap.pk).exists():
        return False
    if any(
        order.status != TransferOrderStatus.PENDING_SIGNATURE or order.filled_quantity < swap.share_amount
        for order in orders.values()
    ):
        return False
    if (
        orders[swap.sell_order_id].matched_order_id != swap.buy_order_id
        or orders[swap.buy_order_id].matched_order_id != swap.sell_order_id
        or SwapOrder.objects.filter(Q(sell_order_id__in=orders) | Q(buy_order_id__in=orders))
        .filter(status__in=ACTIVE_STATES)
        .exclude(pk=swap.pk)
        .exists()
    ):
        return False
    swap.status = SwapOrderStatus.EXPIRED
    swap.save(update_fields=["status", "updated_at"])
    for order in orders.values():
        order.filled_quantity -= swap.share_amount
        order.status = TransferOrderStatus.PARTIALLY_FILLED if order.filled_quantity else TransferOrderStatus.OPEN
        order.save(update_fields=["filled_quantity", "status", "updated_at"])
    publish_trading_event("swap_expired", str(swap.share_token_id))
    return True


def expire_unclaimed_swaps(now=None, batch=500):
    cutoff = now if now is not None else timezone.now()
    candidates = SwapOrder.objects.filter(
        expiry_release_eligible=True,
        expires_at__lt=cutoff,
        status__in=UNCLAIMED_STATES,
        transaction__isnull=True,
        tx_hash="",
    ).order_by("pk")
    checked = expired = 0
    after = None
    while True:
        page = list((candidates.filter(pk__gt=after) if after is not None else candidates)[:batch])
        if not page:
            return {"checked": checked, "expired": expired, "retained": checked - expired}
        for swap in page:
            checked += 1
            expired += expire_unclaimed_swap(swap, cutoff)
        after = page[-1].pk
