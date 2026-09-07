from django.db import transaction

from tokens.services.signing_challenge import spend
from tokens.services.trading_order_service import TradingOrderService


@transaction.atomic
def cancel_signed_order(order, digest, signature):
    challenge = TradingOrderService.verify_order_cancel_signature(
        order=order,
        digest=digest,
        signature=signature,
    )
    cancelled = TradingOrderService.cancel_order(order)
    spend(challenge, signature)

    return cancelled
