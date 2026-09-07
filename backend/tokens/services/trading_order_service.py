import logging
from decimal import Decimal
from typing import Optional

from tokens.exceptions import OrderCancellationException, SignatureRequiredException
from tokens.models import (
    ShareToken,
    SigningChallengePurpose,
    TransferOrder,
    TransferOrderType,
)
from tokens.serializers import TransferOrderDetailSerializer
from tokens.services.signing_challenge import (
    assert_payload_matches,
    challenge_response,
    consume_challenge,
    issue_challenge,
)

logger = logging.getLogger(__name__)


class TradingOrderService:

    @staticmethod
    def verify_order_create_signature(
        wallet_address: str,
        token_uuid: str,
        order_type: str,
        quantity: int,
        price_per_share: Decimal,
        digest: Optional[str],
        signature: Optional[str],
    ):
        if not signature or not digest:
            raise SignatureRequiredException()

        challenge = consume_challenge(
            digest,
            SigningChallengePurpose.ORDER_CREATE,
            wallet_address,
            signature,
        )
        assert_payload_matches(
            challenge,
            {
                "tokenUuid": token_uuid,
                "orderType": order_type,
                "quantity": quantity,
                "pricePerShare": price_per_share,
            },
        )

        return challenge

    @staticmethod
    def verify_order_cancel_signature(
        order: TransferOrder,
        digest: Optional[str],
        signature: Optional[str],
    ):
        if not signature or not digest:
            raise SignatureRequiredException()

        return consume_challenge(
            digest,
            SigningChallengePurpose.ORDER_CANCEL,
            order.wallet_address,
            signature,
            order=order,
        )

    @staticmethod
    def cancel_order(order: TransferOrder) -> TransferOrder:
        if not order.can_cancel:
            raise OrderCancellationException(f"Order with status '{order.get_status_display()}' cannot be cancelled.")

        order.cancel()
        logger.info(f"Cancelled order: {order.uuid}")

        from tokens.events import publish_trading_event

        publish_trading_event("order_cancelled", str(order.token.uuid))
        return order

    @staticmethod
    def get_order_create_message(token, wallet_address, order_type, quantity, price_per_share) -> dict:
        challenge = issue_challenge(
            SigningChallengePurpose.ORDER_CREATE,
            wallet_address,
            {
                "tokenUuid": str(token.uuid),
                "orderType": order_type,
                "quantity": str(quantity),
                "pricePerShare": str(price_per_share),
            },
            verifying_contract=token.contract_address,
        )

        return {
            "token_uuid": str(token.uuid),
            "wallet_address": challenge.wallet_address,
            **challenge_response(challenge),
        }

    @staticmethod
    def get_order_cancel_message(order: TransferOrder) -> dict:
        if not order.can_cancel:
            raise OrderCancellationException(f"Order with status '{order.get_status_display()}' cannot be cancelled.")

        challenge = issue_challenge(
            SigningChallengePurpose.ORDER_CANCEL,
            order.wallet_address,
            {"orderUuid": str(order.uuid)},
            verifying_contract=order.token.contract_address,
            order=order,
        )

        return {
            "order_uuid": str(order.uuid),
            "wallet_address": challenge.wallet_address,
            **challenge_response(challenge),
        }

    @staticmethod
    def build_order_response(order: TransferOrder, match_result: Optional[dict] = None) -> dict:
        response_data = TransferOrderDetailSerializer(order).data

        if match_result:
            response_data["match"] = {
                "matched": True,
                "counter_order": str(
                    match_result["buy_order"].uuid
                    if order.order_type == TransferOrderType.SELL
                    else match_result["sell_order"].uuid
                ),
                "swap_order": str(match_result["swap_order"].uuid),
            }

        return response_data

    @staticmethod
    def get_order_book(token: ShareToken) -> dict:
        buy_levels = TransferOrder.objects.order_book_levels(token, TransferOrderType.BUY)
        sell_levels = TransferOrder.objects.order_book_levels(token, TransferOrderType.SELL)

        logger.info(
            f"Order book fetched for {token.symbol}: {len(buy_levels)} buy levels, {len(sell_levels)} sell levels"
        )

        return {
            "token": str(token.uuid),
            "buy_orders": [
                {
                    "price": str(o["price_per_share"]),
                    "quantity": o["total_quantity"],
                    "orders": o["order_count"],
                }
                for o in buy_levels
            ],
            "sell_orders": [
                {
                    "price": str(o["price_per_share"]),
                    "quantity": o["total_quantity"],
                    "orders": o["order_count"],
                }
                for o in sell_levels
            ],
        }
