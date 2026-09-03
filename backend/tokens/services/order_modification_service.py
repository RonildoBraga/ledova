import logging
import time
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from web3 import Web3

from shared.utils.signature import (
    generate_order_modify_message,
    parse_order_modify_message,
    recover_address_from_signature,
)
from tokens.exceptions import (
    OrderModificationConflictException,
    OrderModificationException,
)
from tokens.models import OrderModificationLog, TransferOrder, TransferOrderType
from tokens.services.matching_service import MatchingService
from tokens.services.share_token_service import ShareTokenService

logger = logging.getLogger(__name__)


class OrderModificationService:

    def validate_can_modify(self, order: TransferOrder) -> None:
        if not order.can_be_modified:
            raise OrderModificationException(f"Order with status '{order.get_status_display()}' cannot be modified.")

        if order.has_pending_swap:
            raise OrderModificationConflictException(
                "Cannot modify order with pending swap. Complete or cancel the swap first."
            )

    def validate_modifications(
        self,
        order: TransferOrder,
        new_quantity: Optional[int] = None,
        new_min_quantity: Optional[int] = None,
        new_price: Optional[Decimal] = None,
    ) -> list[str]:
        errors = []

        effective_quantity = new_quantity if new_quantity is not None else order.quantity
        effective_min_qty = new_min_quantity if new_min_quantity is not None else order.min_quantity
        effective_price = new_price if new_price is not None else order.price_per_share

        if effective_quantity <= order.filled_quantity:
            errors.append(f"New quantity ({effective_quantity}) must exceed filled amount ({order.filled_quantity})")

        remaining = effective_quantity - order.filled_quantity
        if effective_min_qty > remaining:
            errors.append(f"Min quantity ({effective_min_qty}) cannot exceed remaining ({remaining})")

        if effective_min_qty < 0:
            errors.append("Min quantity cannot be negative")

        if effective_price <= 0:
            errors.append("Price must be positive")

        if order.order_type == TransferOrderType.SELL and new_quantity is not None and new_quantity > order.quantity:
            additional_needed = new_quantity - order.quantity
            available_balance = self._get_available_balance(order)
            if additional_needed > available_balance:
                errors.append(
                    f"Insufficient token balance. Need {additional_needed} more, have {available_balance} available."
                )

        return errors

    def generate_modification_message(
        self,
        order: TransferOrder,
        new_quantity: Optional[int] = None,
        new_min_quantity: Optional[int] = None,
        new_price: Optional[Decimal] = None,
    ) -> dict:
        self.validate_can_modify(order)

        effective_quantity = new_quantity if new_quantity is not None else order.quantity
        effective_min_qty = new_min_quantity if new_min_quantity is not None else order.min_quantity
        effective_price = new_price if new_price is not None else order.price_per_share

        errors = self.validate_modifications(order, effective_quantity, effective_min_qty, effective_price)
        if errors:
            raise OrderModificationException("; ".join(errors))

        nonce = int(time.time() * 1000)

        message = generate_order_modify_message(
            order_uuid=str(order.uuid),
            token_symbol=order.token.symbol,
            order_type=order.order_type.upper(),
            new_quantity=effective_quantity,
            new_min_quantity=effective_min_qty,
            new_price_per_share=str(effective_price),
            wallet_address=order.wallet_address,
            nonce=nonce,
        )

        message_hash = Web3.keccak(text=message).hex()

        return {
            "message": message,
            "message_hash": message_hash,
            "order_uuid": str(order.uuid),
            "nonce": nonce,
            "current_values": {
                "quantity": order.quantity,
                "min_quantity": order.min_quantity,
                "price_per_share": str(order.price_per_share),
                "filled_quantity": order.filled_quantity,
                "remaining_quantity": order.remaining_quantity,
            },
            "new_values": {
                "quantity": effective_quantity,
                "min_quantity": effective_min_qty,
                "price_per_share": str(effective_price),
            },
        }

    def verify_signature(self, message: str, signature: str, expected_address: str) -> str:
        signer = recover_address_from_signature(message, signature)
        if not signer:
            raise OrderModificationException("Invalid signature - could not recover signer address")

        if signer.lower() != expected_address.lower():
            raise OrderModificationException("Signature must be from order owner")

        return signer

    @transaction.atomic
    def apply_modification(
        self,
        order: TransferOrder,
        message: str,
        signature: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[TransferOrder, list[dict]]:
        order = TransferOrder.objects.select_for_update().get(uuid=order.uuid)

        self.validate_can_modify(order)

        signer = self.verify_signature(message, signature, order.wallet_address)

        try:
            modifications = parse_order_modify_message(message)
            new_price = Decimal(modifications.get("new_price_per_share", str(order.price_per_share)))
        except Exception as e:
            raise OrderModificationException(f"Invalid message format: {str(e)}")

        if modifications.get("order_uuid") != str(order.uuid):
            raise OrderModificationException("Message is for a different order")

        new_quantity = modifications.get("new_quantity", order.quantity)
        new_min_quantity = modifications.get("new_min_quantity", order.min_quantity)

        errors = self.validate_modifications(order, new_quantity, new_min_quantity, new_price)
        if errors:
            raise OrderModificationException("; ".join(errors))

        order.record_original_values()

        changes = []

        if new_quantity != order.quantity:
            changes.append(
                {
                    "field": "quantity",
                    "old": str(order.quantity),
                    "new": str(new_quantity),
                }
            )
            order.quantity = new_quantity

        if new_min_quantity != order.min_quantity:
            changes.append(
                {
                    "field": "min_quantity",
                    "old": str(order.min_quantity),
                    "new": str(new_min_quantity),
                }
            )
            order.min_quantity = new_min_quantity

        if new_price != order.price_per_share:
            changes.append(
                {
                    "field": "price_per_share",
                    "old": str(order.price_per_share),
                    "new": str(new_price),
                }
            )
            order.price_per_share = new_price

        order.modification_count += 1
        order.last_modified_at = timezone.now()
        order.current_signature = signature
        order.save()

        OrderModificationLog.objects.bulk_create(
            OrderModificationLog(
                order=order,
                field_name=change["field"],
                old_value=change["old"],
                new_value=change["new"],
                modification_message=message,
                signature=signature,
                signer_address=signer,
                ip_address=ip_address,
                user_agent=(user_agent or "")[:500],
            )
            for change in changes
        )

        logger.info(f"Modified order {order.uuid}: {len(changes)} field(s) changed")

        from tokens.events import publish_trading_event

        publish_trading_event("order_modified", str(order.token.uuid))

        return order, changes

    def check_for_matches_after_modification(self, order: TransferOrder) -> Optional[dict]:
        if order.remaining_quantity <= 0:
            return None

        matching_service = MatchingService()
        matched_order = matching_service.find_best_match_with_partial_fill(order)

        if matched_order:
            return {
                "matched_order_uuid": str(matched_order.uuid),
                "matched_quantity": min(order.remaining_quantity, matched_order.remaining_quantity),
                "matched_price": str(matched_order.price_per_share),
            }

        return None

    def _get_available_balance(self, order: TransferOrder) -> int:
        try:
            token_service = ShareTokenService()
            total_balance = token_service.get_token_balance(order.token.contract_address, order.wallet_address)
        except Exception as e:
            logger.error(f"Could not fetch balance for {order.wallet_address}: {e}")
            raise OrderModificationException("Unable to verify token balance. Please try again later.")

        committed = TransferOrder.objects.committed_sell_quantity(
            token=order.token,
            wallet_address=order.wallet_address,
            exclude_uuid=order.uuid,
        )

        return max(0, total_balance - committed)

    def get_modification_history(self, order: TransferOrder) -> dict:
        logs = order.modification_logs.all().order_by("-created_at")

        return {
            "order_uuid": str(order.uuid),
            "original_quantity": order.original_quantity,
            "original_price": str(order.original_price) if order.original_price else None,
            "modification_count": order.modification_count,
            "modifications": [
                {
                    "uuid": str(log.uuid),
                    "field_name": log.field_name,
                    "old_value": log.old_value,
                    "new_value": log.new_value,
                    "signer_address": log.signer_address,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
        }
