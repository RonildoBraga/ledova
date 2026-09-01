import logging
from decimal import Decimal
from typing import Optional

from shared.utils import (
    LoggingContext,
    generate_order_cancel_message,
    generate_order_create_message,
    verify_signature,
)
from tokens.exceptions import (
    InvalidSignatureException,
    OrderCancellationException,
    SignatureRequiredException,
)
from tokens.models import ShareToken, TransferOrder, TransferOrderType
from tokens.serializers import TransferOrderDetailSerializer

logger = logging.getLogger(__name__)


class TradingOrderService:

    @staticmethod
    def verify_order_create_signature(
        wallet_address: str,
        token_uuid: str,
        order_type: str,
        quantity: int,
        price_per_share: Decimal,
        message: Optional[str],
        signature: Optional[str],
    ) -> None:
        if not signature or not message:
            raise SignatureRequiredException()

        expected_message = generate_order_create_message(
            wallet_address=wallet_address,
            token_uuid=token_uuid,
            order_type=order_type,
            quantity=quantity,
            price_per_share=str(price_per_share),
        )

        if message != expected_message:
            raise InvalidSignatureException(f"Invalid message. Expected: '{expected_message}'")

        if not verify_signature(message, signature, wallet_address):
            raise InvalidSignatureException(
                "Signature does not match the wallet address. "
                "Please sign with the wallet that will place this order."
            )

        logger.info(
            f"{LoggingContext.ORDER_CREATE} Signature verified for {wallet_address[:10]}... "
            f"creating {order_type} order"
        )

    @staticmethod
    def verify_order_cancel_signature(
        order: TransferOrder,
        message: Optional[str],
        signature: Optional[str],
    ) -> None:
        if not order.can_cancel:
            raise OrderCancellationException(f"Order with status '{order.get_status_display()}' cannot be cancelled.")

        if not signature or not message:
            raise SignatureRequiredException()

        expected_message = generate_order_cancel_message(str(order.uuid))

        if message != expected_message:
            raise InvalidSignatureException(f"Invalid message. Expected: '{expected_message}'")

        if not verify_signature(message, signature, order.wallet_address):
            raise InvalidSignatureException("Signature does not match the wallet address that created this order.")

        logger.info(f"{LoggingContext.ORDER_CANCEL} Signature verified for order {order.uuid}")

    @staticmethod
    def cancel_order(order: TransferOrder) -> TransferOrder:
        if not order.can_cancel:
            raise OrderCancellationException(f"Order with status '{order.get_status_display()}' cannot be cancelled.")

        order.cancel()
        logger.info(f"{LoggingContext.ORDER_CANCEL} Cancelled order: {order.uuid}")

        from tokens.events import publish_trading_event

        publish_trading_event("order_cancelled", str(order.token.uuid))
        return order

    @staticmethod
    def get_order_create_message(
        wallet_address: str,
        token_uuid: str,
        order_type: str,
        quantity: int,
        price_per_share: Decimal,
    ) -> dict:
        message = generate_order_create_message(
            wallet_address=wallet_address,
            token_uuid=token_uuid,
            order_type=order_type,
            quantity=quantity,
            price_per_share=str(price_per_share),
        )

        return {
            "wallet_address": wallet_address,
            "token_uuid": token_uuid,
            "order_type": order_type,
            "quantity": quantity,
            "price_per_share": str(price_per_share),
            "message": message,
            "instructions": (
                "Sign this message with your wallet to prove ownership. "
                "Then POST to /create/ with the signature and message fields."
            ),
        }

    @staticmethod
    def get_order_cancel_message(order: TransferOrder) -> dict:
        if not order.can_cancel:
            raise OrderCancellationException(f"Order with status '{order.get_status_display()}' cannot be cancelled.")

        message = generate_order_cancel_message(str(order.uuid))

        return {
            "order_uuid": str(order.uuid),
            "wallet_address": order.wallet_address,
            "message": message,
            "instructions": (
                "Sign this message with your wallet to prove ownership. " "Then POST to /cancel/ with the signature."
            ),
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
            f"{LoggingContext.ORDER} Order book fetched for {token.symbol}: "
            f"{len(buy_levels)} buy levels, {len(sell_levels)} sell levels"
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
