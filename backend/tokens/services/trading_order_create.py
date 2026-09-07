from django.db import transaction

from tokens.services.signing_challenge import spend
from tokens.services.trading_order_service import TradingOrderService


@transaction.atomic
def verify_and_spend_create(data, digest, signature) -> None:
    challenge = TradingOrderService.verify_order_create_signature(
        wallet_address=data["wallet_address"],
        token_uuid=str(data["token"].uuid),
        order_type=data["order_type"],
        quantity=data["quantity"],
        price_per_share=data["price_per_share"],
        digest=digest,
        signature=signature,
    )
    spend(challenge, signature)
