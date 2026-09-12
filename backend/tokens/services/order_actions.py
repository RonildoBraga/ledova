import re
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from web3 import Web3

from shared.db import atomic, current_alias
from shared.utils.typed_data import build_domain
from tokens.constants import ORDER_ACTION_REFUSAL_DETAIL_LIMIT
from tokens.exceptions import (
    ChallengeMismatchException,
    OrderActionConflictException,
    OrderActionContextException,
    OrderCancellationException,
    OrderModificationConflictException,
    OrderModificationException,
)
from tokens.models import (
    OrderActionPurpose,
    OrderActionStatus,
    OrderActionSubmission,
    ShareToken,
    TransferOrder,
)
from tokens.services.order_modification_service import (
    apply_order_modification,
    available_modification_balance,
    validate_can_modify,
    validate_modifications,
)
from tokens.services.signing_challenge import (
    CHALLENGE_TYPES,
    assert_payload_matches,
    challenge_response,
    consume_challenge,
    issue_challenge,
    spend,
)
from tokens.services.trading_order_create import _lock_authorized_wallet

NOT_FOUND = "Order action not found."
BUSINESS_REFUSALS = {
    OrderCancellationException: (OrderActionPurpose.CANCEL, "order_cancellation_failed", 400),
    OrderModificationException: (OrderActionPurpose.MODIFY, "order_modification_failed", 400),
    OrderModificationConflictException: (OrderActionPurpose.MODIFY, "order_modification_conflict", 409),
}


@dataclass(frozen=True)
class OrderActionResponse:
    action: OrderActionSubmission
    challenge: dict | None = None

    @property
    def http_status(self):
        return self.action.refusal_status if self.action.status == OrderActionStatus.REFUSED else 200


def _independent_boundary():
    connection = connections[current_alias()]
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise ImproperlyConfigured("Order actions require autocommit outside every transaction block.")


def _authorized_order(actor, account_id, order_id, *, lock=False):
    try:
        order_id = UUID(str(order_id))
    except (ValueError, TypeError, AttributeError):
        raise NotFound(NOT_FOUND)
    orders = TransferOrder.objects.visible_to_user(actor).filter(pk=order_id, owner_account_id=account_id)
    if lock:
        orders = TransferOrder.objects.filter(pk__in=orders.values("pk")).select_for_update(of=("self",))
    order = orders.first()
    if order is None:
        raise NotFound(NOT_FOUND)
    return order


def _load_action(actor, account_id, action_id):
    action = (
        OrderActionSubmission.objects.visible_to_user(actor)
        .select_for_update(of=("self",))
        .filter(owner_account_id=account_id, action_id=action_id)
        .first()
    )
    if action is not None:
        _authorize_action(actor, action)
    return action


def _authorize_action(actor, action):
    _lock_authorized_wallet(actor, action)
    order = _authorized_order(actor, action.owner_account_id, action.order_id, lock=True)
    if (
        order.wallet_id != action.wallet_id
        or order.token_id != action.token_id
        or order.wallet_address.lower() != action.wallet_address.lower()
    ):
        raise NotFound(NOT_FOUND)
    action.order = order


def _token_context(order, action=None):
    token = ShareToken.objects.filter(pk=order.token_id).first()
    if (
        token is None
        or not token.is_deployed
        or not Web3.is_address(token.contract_address)
        or int(token.contract_address, 16) == 0
        or settings.BLOCKCHAIN_CHAIN_ID <= 0
        or not Web3.is_address(order.wallet_address)
    ):
        raise OrderActionContextException()
    if action is not None and (
        action.chain_id != settings.BLOCKCHAIN_CHAIN_ID
        or token.contract_address.lower() != action.verifying_contract.lower()
    ):
        raise OrderActionContextException()
    order.token = token
    return token


def _current_values(order):
    return {
        "order_type": order.order_type,
        "quantity": str(order.quantity),
        "min_quantity": str(order.min_quantity),
        "price_per_share": str(order.price_per_share),
        "filled_quantity": str(order.filled_quantity),
        "remaining_quantity": str(order.remaining_quantity),
        "status": order.status,
        "modification_count": order.modification_count,
        "can_cancel": order.can_cancel,
        "can_modify": order.can_be_modified,
    }


def order_action_context(actor, account_id, order_id):
    order = _authorized_order(actor, account_id, order_id)
    token = _token_context(order)
    return {
        "protocol_version": 1,
        "owner_account_uuid": str(order.owner_account_id),
        "order_uuid": str(order.pk),
        "wallet_uuid": str(order.wallet_id),
        "token_uuid": str(order.token_id),
        "wallet_address": Web3.to_checksum_address(order.wallet_address),
        "domain": build_domain(settings.BLOCKCHAIN_CHAIN_ID, token.contract_address),
        "token": {"name": token.name, "symbol": token.symbol, "contract_address": token.contract_address},
        "current_values": _current_values(order),
    }


def _assert_intent(action, order_id, purpose, data, *, modifications=False):
    try:
        order_id = UUID(str(order_id))
    except (ValueError, TypeError, AttributeError):
        raise NotFound(NOT_FOUND)
    if action.order_id != order_id or action.purpose != purpose:
        raise OrderActionConflictException()
    if modifications and (
        action.new_quantity != data["new_quantity"]
        or action.new_min_quantity != data["new_min_quantity"]
        or action.new_price_per_share != data["new_price_per_share"]
    ):
        raise OrderActionConflictException()


def _register_action(actor, order_id, purpose, data):
    with atomic(durable=True):
        action = _load_action(actor, data["owner_account_uuid"], data["action_id"])
        if action is None:
            order = _authorized_order(actor, data["owner_account_uuid"], order_id)
            token = _token_context(order)
            action, _ = OrderActionSubmission.objects.get_or_create(
                owner_account_id=data["owner_account_uuid"],
                action_id=data["action_id"],
                defaults={
                    "purpose": purpose,
                    "order": order,
                    "wallet_id": order.wallet_id,
                    "token": token,
                    "initiated_by": actor,
                    "wallet_address": Web3.to_checksum_address(order.wallet_address),
                    "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
                    "verifying_contract": Web3.to_checksum_address(token.contract_address),
                    "token_metadata": {"name": token.name, "symbol": token.symbol},
                    "review_values": _current_values(order),
                    "new_quantity": data.get("new_quantity") if purpose == OrderActionPurpose.MODIFY else None,
                    "new_min_quantity": data.get("new_min_quantity") if purpose == OrderActionPurpose.MODIFY else None,
                    "new_price_per_share": (
                        data.get("new_price_per_share") if purpose == OrderActionPurpose.MODIFY else None
                    ),
                },
            )
            action = _load_action(actor, data["owner_account_uuid"], data["action_id"])
        if action is None:
            raise NotFound(NOT_FOUND)
        _assert_intent(action, order_id, purpose, data, modifications=purpose == OrderActionPurpose.MODIFY)
        if action.status == OrderActionStatus.PENDING:
            _token_context(action.order, action)
        return action


def _preflight(action, *, executing=False):
    if action.purpose == OrderActionPurpose.CANCEL:
        return None
    try:
        validate_can_modify(action.order)
    except (OrderModificationException, OrderModificationConflictException):
        if executing:
            return None
        raise
    return available_modification_balance(action.order, action.new_quantity)


def _fields(action):
    fields = {
        "actionId": str(action.action_id),
        "protocolVersion": action.protocol_version,
        "ownerAccountUuid": str(action.owner_account_id),
        "walletUuid": str(action.wallet_id),
        "tokenUuid": str(action.token_id),
        "orderUuid": str(action.order_id),
    }
    if action.purpose == OrderActionPurpose.MODIFY:
        fields.update(
            newQuantity=str(action.new_quantity),
            newMinQuantity=str(action.new_min_quantity),
            newPricePerShare=str(action.new_price_per_share),
        )
    return fields


def _validate_issue(action, available_balance):
    if action.purpose == OrderActionPurpose.CANCEL:
        if not action.order.can_cancel:
            raise OrderCancellationException(
                f"Order with status '{action.order.get_status_display()}' cannot be cancelled."
            )
        return
    validate_can_modify(action.order)
    errors = validate_modifications(
        action.order,
        action.new_quantity,
        action.new_min_quantity,
        action.new_price_per_share,
        available_balance=available_balance,
    )
    if errors:
        raise OrderModificationException("; ".join(errors))


def issue_order_action(actor, order_id, purpose, data):
    _independent_boundary()
    action = _register_action(actor, order_id, purpose, data)
    if action.status != OrderActionStatus.PENDING:
        return OrderActionResponse(action)
    available_balance = _preflight(action)
    with atomic(durable=True):
        action = _load_action(actor, data["owner_account_uuid"], data["action_id"])
        if action is None:
            raise NotFound(NOT_FOUND)
        _assert_intent(action, order_id, purpose, data, modifications=purpose == OrderActionPurpose.MODIFY)
        if action.status != OrderActionStatus.PENDING:
            return OrderActionResponse(action)
        _token_context(action.order, action)
        _validate_issue(action, available_balance)
        challenge = issue_challenge(
            "order_" + purpose,
            action.wallet_address,
            _fields(action),
            verifying_contract=action.verifying_contract,
            order=action.order,
            action=action,
        )
        return OrderActionResponse(action, challenge_response(challenge))


def _verify(action, credentials):
    digest, signature = credentials.get("digest"), credentials.get("signature")
    for name, value, pattern in (
        ("digest", digest, r"0x[0-9a-fA-F]{64}"),
        ("signature", signature, r"0x[0-9a-fA-F]{130}"),
    ):
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            raise ValidationError({name: ["A valid signed challenge is required for a pending action."]})
    challenge = consume_challenge(
        digest, "order_" + action.purpose, action.wallet_address, signature, order=action.order, action=action
    )
    if challenge.payload["types"] != CHALLENGE_TYPES["order_" + action.purpose] or challenge.payload[
        "domain"
    ] != build_domain(action.chain_id, action.verifying_contract):
        raise ChallengeMismatchException("action")
    assert_payload_matches(challenge, _fields(action))
    return challenge


def _apply(action, challenge, available_balance, ip_address, user_agent):
    if action.purpose == OrderActionPurpose.CANCEL:
        _validate_issue(action, None)
        previous = action.order.status
        action.order.cancel()
        return {"kind": "cancel", "from_status": previous, "to_status": action.order.status}
    _, changes = apply_order_modification(action.order, challenge, available_balance, ip_address, user_agent)
    return {"kind": "modify", "modification_count": action.order.modification_count, "changes": changes}


def execute_order_action(actor, order_id, purpose, data, credentials, *, ip_address=None, user_agent=None):
    _independent_boundary()
    with atomic():
        action = _load_action(actor, data["owner_account_uuid"], data["action_id"])
        if action is None:
            raise NotFound(NOT_FOUND)
        _assert_intent(action, order_id, purpose, data)
        if action.status != OrderActionStatus.PENDING:
            return OrderActionResponse(action)
        _token_context(action.order, action)
        _verify(action, credentials)
    available_balance = _preflight(action, executing=True)
    with atomic(durable=True):
        action = _load_action(actor, data["owner_account_uuid"], data["action_id"])
        if action is None:
            raise NotFound(NOT_FOUND)
        _assert_intent(action, order_id, purpose, data)
        if action.status != OrderActionStatus.PENDING:
            return OrderActionResponse(action)
        _token_context(action.order, action)
        challenge = _verify(action, credentials)
        spend(challenge, credentials["signature"])
        try:
            with atomic():
                result = _apply(action, challenge, available_balance, ip_address, user_agent)
        except tuple(BUSINESS_REFUSALS) as exc:
            if type(exc) not in BUSINESS_REFUSALS or BUSINESS_REFUSALS[type(exc)][0] != purpose:
                raise
            _, action.refusal_code, action.refusal_status = BUSINESS_REFUSALS[type(exc)]
            action.refusal_detail = str(exc.detail)[:ORDER_ACTION_REFUSAL_DETAIL_LIMIT]
            action.status = OrderActionStatus.REFUSED
        else:
            action.result = result
            action.status = OrderActionStatus.APPLIED
        action.executed_challenge = challenge
        action.executed_by = actor
        action.resolved_at = timezone.now()
        action.save(
            update_fields=[
                "status",
                "result",
                "refusal_code",
                "refusal_detail",
                "refusal_status",
                "executed_challenge",
                "executed_by",
                "resolved_at",
                "updated_at",
            ]
        )
        _authorize_action(actor, action)
        if action.status == OrderActionStatus.APPLIED:
            from tokens.events import publish_trading_event

            publish_trading_event(
                "order_cancelled" if purpose == OrderActionPurpose.CANCEL else "order_modified", str(action.token_id)
            )
        return OrderActionResponse(action)


@atomic()
def recover_order_action(actor, account_id, action_id):
    action = _load_action(actor, account_id, action_id)
    if action is None:
        raise NotFound(NOT_FOUND)
    return OrderActionResponse(action)
