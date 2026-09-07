import logging

from shared.services import act_under_row_lock
from tokens.events import publish_trading_event
from tokens.exceptions import OrderCancellationException
from tokens.models import TransferOrder
from tokens.services.signing_challenge import spend
from tokens.services.trading_order_service import TradingOrderService

logger = logging.getLogger(__name__)


def cancel_signed_order(order, digest, signature):
    return act_under_row_lock(
        TransferOrder.objects.all(),
        order.pk,
        lambda locked: _spend_then_cancel(locked, digest, signature),
    )


def _spend_then_cancel(order: TransferOrder, digest, signature):
    challenge = TradingOrderService.verify_order_cancel_signature(order=order, digest=digest, signature=signature)
    spend(challenge, signature)

    if not order.can_cancel:
        return order, OrderCancellationException(
            f"Order with status '{order.get_status_display()}' cannot be cancelled."
        )

    order.cancel()
    logger.info(f"Cancelled order: {order.uuid}")
    publish_trading_event("order_cancelled", str(order.token.uuid))
    return order, None
