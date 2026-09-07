from django.db import transaction

from tokens.services.signing_challenge import spend
from tokens.services.trading_order_service import TradingOrderService


def cancel_signed_order(order, digest, signature):
    _verify_and_spend(order, digest, signature)

    return TradingOrderService.cancel_order(order)


@transaction.atomic
def _verify_and_spend(order, digest, signature) -> None:
    challenge = TradingOrderService.verify_order_cancel_signature(
        order=order,
        digest=digest,
        signature=signature,
    )
    spend(challenge, signature)
