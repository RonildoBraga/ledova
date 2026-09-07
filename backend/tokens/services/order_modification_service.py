import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from tokens.exceptions import (
    OrderModificationConflictException,
    OrderModificationException,
)
from tokens.models import (
    OrderModificationLog,
    SigningChallengePurpose,
    TransferOrder,
    TransferOrderStatus,
    TransferOrderType,
)
from tokens.services.share_token_service import ShareTokenService
from tokens.services.signing_challenge import (
    challenge_response,
    consume_challenge,
    issue_challenge,
    spend,
)

logger = logging.getLogger(__name__)


class OrderModificationService:

    def validate_can_modify(self, order: TransferOrder) -> None:
        if order.has_pending_swap:
            raise OrderModificationConflictException(
                "Cannot modify order with pending swap. Complete or cancel the swap first."
            )

        if order.status not in (TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED):
            raise OrderModificationException(f"Order with status '{order.get_status_display()}' cannot be modified.")

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

        challenge = issue_challenge(
            SigningChallengePurpose.ORDER_MODIFY,
            order.wallet_address,
            {
                "orderUuid": str(order.uuid),
                "newQuantity": str(effective_quantity),
                "newMinQuantity": str(effective_min_qty),
                "newPricePerShare": str(effective_price),
            },
            verifying_contract=order.token.contract_address,
            order=order,
        )

        return {
            "order_uuid": str(order.uuid),
            **challenge_response(challenge),
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

    @transaction.atomic
    def apply_modification(
        self,
        order: TransferOrder,
        digest: str,
        signature: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[TransferOrder, list[dict]]:
        order = TransferOrder.objects.select_for_update().get(uuid=order.uuid)

        challenge = consume_challenge(
            digest,
            SigningChallengePurpose.ORDER_MODIFY,
            order.wallet_address,
            signature,
            order=order,
        )
        spend(challenge, signature)
        signer = challenge.wallet_address

        self.validate_can_modify(order)

        intent = challenge.payload["message"]
        new_quantity = int(intent["newQuantity"])
        new_min_quantity = int(intent["newMinQuantity"])
        new_price = Decimal(intent["newPricePerShare"])

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
                challenge=challenge,
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
