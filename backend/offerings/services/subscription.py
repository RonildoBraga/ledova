import logging
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import IntegrityError
from django.utils import timezone

from offerings.exceptions import (
    InvalidSubscriptionTransitionException,
    SubscriptionRefusedException,
)
from offerings.models import (
    MONEY_ALREADY_IN,
    Offering,
    SettlementRail,
    Subscription,
    SubscriptionStatus,
)
from offerings.services.payments import (
    REFERENCE_ATTEMPTS,
    generate_reference,
    normalize_tx_hash,
    raw_settlement_amount,
)
from operators.models import Operator
from shared.db import atomic
from tokens.models import IssuanceType, RequestStatus, ShareIssuanceRequest
from tokens.services import ShareTokenService
from users.services.eligibility import require_subscription_eligibility

logger = logging.getLogger(__name__)

DEFAULT_PAYMENT_WINDOW = timedelta(days=7)
CLAIMED_STATUSES = (RequestStatus.EXECUTING, RequestStatus.EXECUTED)

OFFERING_NOT_OPEN = "The {symbol} offering is not open for subscription."
BELOW_MINIMUM = "The {symbol} offering asks for at least {minimum} shares; this subscription asks for {quantity}."
ABOVE_MAXIMUM = "The {symbol} offering allows at most {maximum} shares per investor; this one asks for {quantity}."
ABOVE_CAP = "The {symbol} offering is capped at {cap} shares; this one asks for {quantity}."
WALLET_NOT_ON_ACCOUNT = "That wallet does not belong to the subscribing account."
RAIL_NOT_OFFERED = "The {symbol} offering does not settle by {rail}."
ASSET_NOT_OFFERED = "{symbol} is not a settlement asset of this offering."
ASSET_REQUIRED = "A stablecoin settlement must name the settlement asset."
EXPIRY_NOTE = "Payment was not received by {due}; the subscription lapsed."
EXPIRY_LEFT_ALONE = (
    "Subscription {reference} is past its payment due date but money has landed against it since the sweep "
    "read the row; it stays open for an operator instead of being closed over the payment: {detail}"
)
TX_HASH_REQUIRED = "A stablecoin payment must carry the transfer hash, so one transfer cannot fund two subscriptions."
TX_HASH_ALREADY_USED = "{tx_hash} already funds another subscription."
RECEIVED_NOT_POSITIVE = "The amount received must be greater than zero."
REFUND_NOT_POSITIVE = (
    "A refund must be greater than zero. Recording a zero or negative refund would close the money out of the "
    "record without returning a cent of it."
)
REFUND_ABOVE_HELD = (
    "{amount} is more than the {refundable} still returnable against {reference}: {received} arrived and "
    "{refunded} has already gone back."
)
PAYMENT_RESTATED_DOWN = (
    "The amount received against {reference} was restated down from {before} to {after}. The row now carries only "
    "{after}; the earlier figure survives in the preceding entry of this row's admin history."
)
REFERENCE_SEEN_REUSED = (
    "That statement line is already recorded against {others}. Bank settlement is operator-attested so this is "
    "not refused, but one line must not fund two subscriptions: check the statement before allotting."
)
NOTHING_COVERED = (
    "{received} covers no whole share at {price} each. Refund it instead of accepting it as the final payment."
)
ALREADY_ALLOTTED = "This subscription already has issuance request {uuid}; it cannot be allotted twice."
NOT_PAID = "Only a paid subscription can be allotted; this one is {status}."
NOTHING_TO_ALLOT = "This subscription has been scaled back to zero shares; refund it instead."
ALLOTMENT_ABOVE_HEADROOM = (
    "Allotting {amount} shares of {symbol} would exceed the {room} still available "
    "({cap_room} left under the offering cap, {chain_room} left of the authorized supply)."
)
BATCH_ABOVE_HEADROOM = (
    "Allotting {total} shares of {symbol} would exceed the {room} still available "
    "({cap_room} left under the offering cap, {chain_room} left of the authorized supply). "
    "The whole batch is refused; scale back first rather than allotting a first-come subset."
)
NOT_RETRYABLE = "Issuance request {uuid} is {status}; there is nothing to retry."
NO_REQUEST_TO_RETRY = "This subscription has no issuance request yet; allot it first."
ISSUANCE_ALREADY_CLAIMED = (
    "Issuance request {uuid} is {status}, so the shares are already claimed on chain. "
    "{verb} is refused while that mint stands; the money cannot go back while the shares stay out."
)
ISSUANCE_REFUSED_BY_REFUND = "Refused: subscription {reference} was refunded before the shares were minted."
MINT_BROADCAST = (
    "Issuance request {uuid} broadcast mint {tx_hash} and never confirmed it, so those shares may be out. "
    "{verb} is refused until that mint is resolved: the executing sweep completes it if it was mined and "
    "clears the hash if it reverted, and only then is the money free to move."
)


def _quantize(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def amount_for(offering: Offering, quantity: int) -> Decimal:
    return _quantize(Decimal(quantity) * offering.price_per_share)


def _check_bounds(offering: Offering, quantity: int) -> None:
    symbol = offering.token.symbol
    if quantity < offering.minimum_shares:
        raise SubscriptionRefusedException(
            BELOW_MINIMUM.format(symbol=symbol, minimum=offering.minimum_shares, quantity=quantity)
        )
    if offering.maximum_shares is not None and quantity > offering.maximum_shares:
        raise SubscriptionRefusedException(
            ABOVE_MAXIMUM.format(symbol=symbol, maximum=offering.maximum_shares, quantity=quantity)
        )
    if quantity > offering.cap_shares:
        raise SubscriptionRefusedException(ABOVE_CAP.format(symbol=symbol, cap=offering.cap_shares, quantity=quantity))


def _require_open(offering: Offering) -> None:
    if not offering.is_open:
        raise SubscriptionRefusedException(OFFERING_NOT_OPEN.format(symbol=offering.token.symbol))


def create_draft(offering: Offering, user_account, wallet, quantity: int, submitted_by=None) -> Subscription:
    _require_open(offering)
    _check_bounds(offering, quantity)
    if wallet.user_account_id != user_account.pk:
        raise SubscriptionRefusedException(WALLET_NOT_ON_ACCOUNT)
    return Subscription.objects.create(
        offering=offering,
        user_account=user_account,
        wallet=wallet,
        submitted_by=submitted_by,
        quantity=quantity,
        price_per_share=offering.price_per_share,
        amount_due=amount_for(offering, quantity),
    )


def _require_eligible(subscription: Subscription):
    return require_subscription_eligibility(
        subscription.user_account, subscription.offering.token.company, subscription.amount_due
    )


@atomic()
def submit(subscription: Subscription, submitted_by=None) -> Subscription:
    _require_open(subscription.offering)
    _check_bounds(subscription.offering, subscription.quantity)
    _require_eligible(subscription)
    subscription.submit(submitted_by=submitted_by)
    logger.info(f"Subscription {subscription.uuid} submitted for {subscription.offering.token.symbol}")
    return subscription


@atomic()
def accept(subscription: Subscription) -> Subscription:
    _require_eligible(subscription)
    subscription.accept()
    return subscription


def _rail_asset(offering: Offering, rail: str, settlement_asset):
    if rail == SettlementRail.BANK_TRANSFER:
        if not offering.accepts_bank_transfer:
            raise SubscriptionRefusedException(
                RAIL_NOT_OFFERED.format(symbol=offering.token.symbol, rail="bank transfer")
            )
        return None
    if settlement_asset is None:
        raise SubscriptionRefusedException(ASSET_REQUIRED)
    if not offering.settlement_assets.filter(pk=settlement_asset.pk).exists():
        raise SubscriptionRefusedException(ASSET_NOT_OFFERED.format(symbol=settlement_asset.symbol))
    return settlement_asset


def _due_at(offering: Offering, due_at):
    moment = due_at or timezone.now() + DEFAULT_PAYMENT_WINDOW
    if offering.closes_at is not None and moment > offering.closes_at:
        return offering.closes_at
    return moment


def issue_instruction(subscription: Subscription, rail: str, settlement_asset=None, due_at=None) -> Subscription:
    offering = subscription.offering
    asset = _rail_asset(offering, rail, settlement_asset)
    amount = None if asset is None else raw_settlement_amount(subscription.amount_due, asset)[0]
    moment = _due_at(offering, due_at)
    operator = Operator.get()

    for attempt in range(REFERENCE_ATTEMPTS):
        try:
            with atomic():
                subscription.mark_awaiting_payment(
                    rail=rail,
                    settlement_asset=asset,
                    settlement_amount=amount,
                    reference=generate_reference(operator),
                    due_at=moment,
                )
            return subscription
        except IntegrityError:
            logger.warning(f"Payment reference collided for subscription {subscription.uuid}, attempt {attempt + 1}")
            subscription.refresh_from_db()
    raise SubscriptionRefusedException(f"Could not issue a unique payment reference after {REFERENCE_ATTEMPTS} tries.")


def _scaled_quantity(subscription: Subscription, received: Decimal) -> int:
    covered = (received / subscription.price_per_share).to_integral_value(rounding=ROUND_DOWN)
    return min(subscription.quantity, int(covered))


def _locked(subscription: Subscription) -> Subscription:
    return Subscription.objects.select_for_update().get(pk=subscription.pk)


@atomic()
def confirm_payment(
    subscription: Subscription,
    confirmed_by,
    amount_received: Decimal,
    received_on,
    reference_seen: str = "",
    tx_hash: str = "",
    notes: str = "",
    accept_as_final: bool = False,
) -> Subscription:
    locked = _locked(subscription)
    received = _quantize(amount_received)
    if received <= 0:
        raise SubscriptionRefusedException(RECEIVED_NOT_POSITIVE)
    _refuse_if_issuance_claimed(locked, "Restating the payment")
    tx_hash = normalize_tx_hash(tx_hash)
    if locked.settlement_rail == SettlementRail.STABLECOIN and not tx_hash:
        raise SubscriptionRefusedException(TX_HASH_REQUIRED)
    if tx_hash and Subscription.objects.filter(payment_tx_hash=tx_hash).exclude(pk=locked.pk).exists():
        raise SubscriptionRefusedException(TX_HASH_ALREADY_USED.format(tx_hash=tx_hash))

    allotted, refund, status = _payment_outcome(locked, received, accept_as_final)
    try:
        with atomic():
            locked.record_payment(
                status=status,
                allotted_quantity=allotted,
                refund_amount=refund,
                confirmed_by=confirmed_by,
                amount_received=received,
                payment_received_on=received_on,
                payment_reference_seen=reference_seen,
                payment_tx_hash=tx_hash,
                payment_notes=notes,
            )
    except IntegrityError as exc:
        if not tx_hash:
            raise
        raise SubscriptionRefusedException(TX_HASH_ALREADY_USED.format(tx_hash=tx_hash)) from exc
    subscription.refresh_from_db()
    return subscription


def subscriptions_sharing_statement_line(subscription: Subscription) -> list[str]:
    line = (subscription.payment_reference_seen or "").strip()
    if not line:
        return []
    others = (
        Subscription.objects.filter(payment_reference_seen__iexact=line)
        .exclude(pk=subscription.pk)
        .exclude(status__in=[SubscriptionStatus.REJECTED, SubscriptionStatus.WITHDRAWN])
        .order_by("created_at")
    )
    return [row.reference or str(row.uuid) for row in others]


def payment_warnings(subscription: Subscription, previous_amount) -> list[str]:
    warnings = []
    if previous_amount is not None and subscription.amount_received < previous_amount:
        warnings.append(
            PAYMENT_RESTATED_DOWN.format(
                reference=subscription.reference or subscription.uuid,
                before=previous_amount,
                after=subscription.amount_received,
            )
        )
    others = subscriptions_sharing_statement_line(subscription)
    if others:
        warnings.append(REFERENCE_SEEN_REUSED.format(others=", ".join(others)))
    return warnings


def _payment_outcome(subscription: Subscription, received: Decimal, accept_as_final: bool):
    if received >= subscription.amount_due:
        overpaid = received - subscription.amount_due
        return subscription.allotted_quantity, (overpaid or None), SubscriptionStatus.PAID
    if not accept_as_final:
        return subscription.allotted_quantity, subscription.refund_amount, SubscriptionStatus.AWAITING_PAYMENT
    allotted = _scaled_quantity(subscription, received)
    if allotted < 1:
        raise SubscriptionRefusedException(
            NOTHING_COVERED.format(received=received, price=subscription.price_per_share)
        )
    residual = received - _quantize(Decimal(allotted) * subscription.price_per_share)
    return allotted, (residual or None), SubscriptionStatus.PAID


def _linked_request(subscription: Subscription):
    if subscription.issuance_request_id is None:
        return None
    return ShareIssuanceRequest.objects.get(pk=subscription.issuance_request_id)


def _already_claimed(request: ShareIssuanceRequest, verb: str) -> SubscriptionRefusedException:
    return SubscriptionRefusedException(
        ISSUANCE_ALREADY_CLAIMED.format(uuid=request.uuid, status=request.get_status_display().lower(), verb=verb)
    )


def _refuse_if_the_mint_is_out(request: ShareIssuanceRequest, verb: str) -> None:
    if request.status in CLAIMED_STATUSES:
        raise _already_claimed(request, verb)
    issuance = ShareTokenService.broadcast_mint(request)
    if issuance is not None:
        raise SubscriptionRefusedException(
            MINT_BROADCAST.format(uuid=request.uuid, tx_hash=issuance.tx_hash, verb=verb)
        )


def _refuse_if_issuance_claimed(subscription: Subscription, verb: str) -> None:
    request = _linked_request(subscription)
    if request is None:
        return
    _refuse_if_the_mint_is_out(request, verb)
    if request.status == RequestStatus.REJECTED:
        return
    raise _already_claimed(request, verb)


def _refuse_the_issuance(subscription: Subscription, verb: str) -> None:
    request = _linked_request(subscription)
    if request is None:
        return
    _refuse_if_the_mint_is_out(request, verb)
    if request.status == RequestStatus.REJECTED:
        return
    now = timezone.now()
    claimed = ShareIssuanceRequest.objects.filter(
        pk=request.pk, status__in=ShareIssuanceRequest.EXECUTABLE_STATUSES
    ).update(
        status=RequestStatus.REJECTED,
        rejection_reason=ISSUANCE_REFUSED_BY_REFUND.format(reference=subscription.reference or subscription.uuid),
        reviewed_at=now,
        updated_at=now,
    )
    if claimed:
        logger.info(f"Issuance request {request.uuid} rejected because subscription {subscription.uuid} was refunded")
        return
    request.refresh_from_db(fields=["status"])
    raise _already_claimed(request, verb)


@atomic()
def record_refund(subscription: Subscription, amount: Decimal, reference: str = "", notes: str = "") -> Subscription:
    locked = _locked(subscription)
    value = _quantize(amount)
    if value <= 0:
        raise SubscriptionRefusedException(REFUND_NOT_POSITIVE)
    refundable = locked.amount_refundable
    if not (locked.status == SubscriptionStatus.ALLOTTED and value <= refundable):
        _refuse_the_issuance(locked, "A refund")
    if value > refundable:
        raise SubscriptionRefusedException(
            REFUND_ABOVE_HELD.format(
                amount=value,
                refundable=refundable,
                reference=locked.reference or locked.uuid,
                received=locked.amount_received or Decimal("0.00"),
                refunded=locked.refunded_total,
            )
        )
    locked.mark_refunded(amount=value, reference=reference, notes=notes)
    subscription.refresh_from_db()
    logger.info(f"Refund of {value} recorded against subscription {subscription.uuid}")
    return subscription


def _refuse_if_money_in(subscription: Subscription) -> None:
    if subscription.has_money_in:
        raise SubscriptionRefusedException(
            MONEY_ALREADY_IN.format(
                amount=subscription.money_held, reference=subscription.reference or subscription.uuid
            )
        )


@atomic()
def reject(subscription: Subscription, reason: str) -> Subscription:
    locked = _locked(subscription)
    _refuse_if_issuance_claimed(locked, "Rejecting it")
    _refuse_if_money_in(locked)
    locked.reject(notes=reason)
    subscription.refresh_from_db()
    return subscription


@atomic()
def withdraw(subscription: Subscription, reason: str = "") -> Subscription:
    locked = _locked(subscription)
    _refuse_if_issuance_claimed(locked, "Withdrawing it")
    _refuse_if_money_in(locked)
    locked.withdraw(notes=reason)
    subscription.refresh_from_db()
    return subscription


def expire_overdue(moment, limit: int) -> dict:
    expired = 0
    left_alone = []
    for subscription in Subscription.objects.unpaid_past_due(moment)[:limit]:
        reference = subscription.reference or str(subscription.uuid)
        try:
            reject(subscription, EXPIRY_NOTE.format(due=subscription.payment_due_at.isoformat()))
        except (SubscriptionRefusedException, InvalidSubscriptionTransitionException) as exc:
            left_alone.append(reference)
            logger.warning(EXPIRY_LEFT_ALONE.format(reference=reference, detail=exc.detail))
            continue
        expired += 1
    return {"expired": expired, "left_alone": left_alone}


def cap_headroom(offering: Offering) -> int:
    committed = Subscription.objects.for_offering(offering).committed_to_shares().share_commitment()
    return offering.cap_shares - committed


def share_supply_snapshot(offering: Offering, service=None) -> tuple[int, int]:
    service = service or ShareTokenService()
    return service.share_supply(offering.token.contract_address)


def _unminted(offering: Offering) -> int:
    return ShareIssuanceRequest.objects.unminted(offering.token).share_total()


def chain_snapshot(offering: Offering, service=None) -> tuple[int, int, int]:
    authorized, issued = share_supply_snapshot(offering, service)
    return authorized, issued, _unminted(offering)


def offering_headroom(offering: Offering, service=None, supply=None) -> tuple[int, int]:
    if supply is None:
        authorized, issued, unminted = chain_snapshot(offering, service)
    else:
        authorized, issued, unminted_when_read = supply
        unminted = max(unminted_when_read, _unminted(offering))
    return cap_headroom(offering), authorized - issued - unminted


def _residual_owed(subscription: Subscription, allotted: int):
    residual = subscription.money_held - _quantize(Decimal(allotted) * subscription.price_per_share)
    return residual if residual > 0 else None


@atomic()
def scale_back(offering: Offering) -> dict:
    locked = Offering.objects.select_for_update().get(pk=offering.pk)
    pending = list(Subscription.objects.for_offering(locked).awaiting_allotment().order_by("created_at"))
    requested = sum(subscription.allotment_quantity for subscription in pending)
    room = cap_headroom(locked)
    if requested <= room or requested == 0:
        return {"scaled": 0, "requested": requested, "room": room}

    scaled = 0
    for subscription in pending:
        base = subscription.allotment_quantity
        allotted = max(min(base, base * room // requested), 0)
        if allotted == base:
            continue
        subscription.allotted_quantity = allotted
        subscription.refund_amount = _residual_owed(subscription, allotted)
        subscription.save(update_fields=["allotted_quantity", "refund_amount", "updated_at"])
        scaled += 1
    logger.info(f"Scaled {scaled} subscriptions of {locked.token.symbol} from {requested} into {room} shares")
    return {"scaled": scaled, "requested": requested, "room": room}


def _not_allottable(subscription: Subscription):
    if subscription.issuance_request_id is not None:
        return ALREADY_ALLOTTED.format(uuid=subscription.issuance_request_id)
    if subscription.status != SubscriptionStatus.PAID:
        return NOT_PAID.format(status=subscription.get_status_display().lower())
    if subscription.allotment_quantity < 1:
        return NOTHING_TO_ALLOT
    return None


@atomic()
def allot(subscription: Subscription, operator_user, notes: str = "", headroom=None):
    from offerings.tasks import allot_subscription_task

    supply = None if headroom is not None else chain_snapshot(subscription.offering)
    offering = Offering.objects.select_for_update().select_related("token").get(pk=subscription.offering_id)
    locked = _locked(subscription)
    refusal = _not_allottable(locked)
    if refusal is not None:
        raise SubscriptionRefusedException(refusal)
    amount = locked.allotment_quantity

    cap_room, chain_room = headroom if headroom is not None else offering_headroom(offering, supply=supply)
    room = min(cap_room, chain_room)
    if amount > room:
        raise SubscriptionRefusedException(
            ALLOTMENT_ABOVE_HEADROOM.format(
                amount=amount, symbol=offering.token.symbol, room=room, cap_room=cap_room, chain_room=chain_room
            )
        )

    request = ShareTokenService().create_issuance_request(
        offering.token,
        recipient=locked.wallet.address,
        amount=amount,
        user=operator_user,
        reason=f"Allotment of subscription {locked.reference or locked.uuid}",
        issuance_type=IssuanceType.ADDITIONAL,
    )
    request.approve(operator_user, notes)
    locked.issuance_request = request
    locked.save(update_fields=["issuance_request", "updated_at"])
    subscription.issuance_request = request
    allot_subscription_task.defer(
        subscription_uuid=str(locked.uuid), executed_by=operator_user.pk if operator_user else None
    )
    logger.info(f"Subscription {locked.uuid} allotted {amount} shares through request {request.uuid}")
    return request


def allot_batch(subscriptions, operator_user, notes: str = "", service=None) -> dict:
    service = service or ShareTokenService()
    grouped = {}
    for subscription in subscriptions:
        grouped.setdefault(subscription.offering_id, []).append(subscription)

    result = {"allotted": 0, "refusals": []}
    for offering_id, group in grouped.items():
        allotted, refusals = _allot_group(offering_id, group, operator_user, notes, service)
        result["allotted"] += allotted
        result["refusals"].extend(refusals)
    return result


def _allot_group(offering_id, group, operator_user, notes, service) -> tuple[int, list[str]]:
    ready, refusals = [], []
    for subscription in group:
        refusal = _not_allottable(subscription)
        if refusal is None:
            ready.append(subscription)
        else:
            refusals.append(refusal)
    if not ready:
        return 0, refusals
    try:
        return _allot_ready(offering_id, ready, operator_user, notes, service), refusals
    except SubscriptionRefusedException as exc:
        return 0, refusals + [str(exc.detail)]


def _allot_ready(offering_id, ready, operator_user, notes, service) -> int:
    with atomic():
        offering = Offering.objects.select_for_update().select_related("token").get(pk=offering_id)
        cap_room, chain_room = offering_headroom(offering, service)
        room = min(cap_room, chain_room)
        total = sum(subscription.allotment_quantity for subscription in ready)
        if total > room:
            raise SubscriptionRefusedException(
                BATCH_ABOVE_HEADROOM.format(
                    total=total, symbol=offering.token.symbol, room=room, cap_room=cap_room, chain_room=chain_room
                )
            )
        for subscription in ready:
            allot(subscription, operator_user, notes, headroom=(cap_room, chain_room))
    return len(ready)


def retry_allotment(subscription: Subscription, operator_user) -> Subscription:
    from offerings.tasks import allot_subscription_task

    request = subscription.issuance_request
    if request is None:
        raise SubscriptionRefusedException(NO_REQUEST_TO_RETRY)
    if not request.can_be_executed:
        raise SubscriptionRefusedException(
            NOT_RETRYABLE.format(uuid=request.uuid, status=request.get_status_display().lower())
        )
    allot_subscription_task.defer(
        subscription_uuid=str(subscription.uuid), executed_by=operator_user.pk if operator_user else None
    )
    return subscription


def executed_requests_pending_allotment():
    return Subscription.objects.executed_but_not_allotted().select_related("issuance_request")
