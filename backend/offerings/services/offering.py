import logging
from decimal import Decimal

from django.db import transaction

from offerings.exceptions import OfferingRefusedException
from offerings.models import Offering
from operators.settlement import require_deployment
from tokens.models import ShareIssuance, ShareToken
from users.models.investor_classification import PRODUCT_VALUE_THRESHOLD_AUD
from users.tasks.notifications import send_push_notification

logger = logging.getLogger(__name__)


TOKEN_NOT_DEPLOYED = "{symbol} is not deployed yet, so it has no shares to offer."
COMPANY_NOT_ACTIVE = "{name} must be active before it can offer shares; it is {status}."
NO_PAYMENT_RAIL = "Configure at least one payment rail: bank transfer, a settlement stablecoin, or both."
CAP_ABOVE_HEADROOM = (
    "The cap of {cap} shares exceeds the {headroom} unissued shares left on {symbol} "
    "({authorized} authorized, {issued} issued, {reserved} reserved by other live offerings). "
    "Raise the authorized total with a CapitalIncreaseRequest first."
)
MAXIMUM_ABOVE_CAP = "The maximum of {maximum} shares per investor cannot exceed the cap of {cap} shares."
ALREADY_LIVE = (
    "{symbol} already has an offering in flight ({status}, opening {opens}). Close, reject or withdraw it "
    "before submitting another; one share class carries one live offering at a time."
)
MINIMUM_BELOW_THRESHOLD = (
    "Section 708(8)(a) needs at least AUD {threshold} payable on acceptance; {shares} shares at "
    "{price} is AUD {amount}."
)

ISSUER_NOTIFICATIONS = {
    "submit": ("Offering submitted", "The offering of {name} was submitted for review."),
    "start_review": ("Offering review started", "The review of the {name} offering has started."),
    "approve": ("Offering approved", "The offering of {name} has been approved."),
    "reject": ("Offering rejected", "The offering of {name} was rejected: {reason}"),
    "close": ("Offering closed", "The offering of {name} is now closed."),
    "withdraw": ("Offering withdrawn", "The offering of {name} was withdrawn."),
}


def unissued_headroom(offering: Offering) -> dict:
    token = offering.token
    authorized = int(token.total_supply or 0)
    issued = ShareIssuance.objects.completed_supply(token)
    reserved = sum(
        Offering.objects.for_token(token).live().exclude(pk=offering.pk).values_list("cap_shares", flat=True)
    )
    return {
        "authorized": authorized,
        "issued": issued,
        "reserved": reserved,
        "headroom": authorized - issued - reserved,
    }


def _check_bounds(offering: Offering) -> None:
    room = unissued_headroom(offering)
    if offering.cap_shares > room["headroom"]:
        raise OfferingRefusedException(
            CAP_ABOVE_HEADROOM.format(cap=offering.cap_shares, symbol=offering.token.symbol, **room)
        )
    if offering.maximum_shares is not None and offering.maximum_shares > offering.cap_shares:
        raise OfferingRefusedException(
            MAXIMUM_ABOVE_CAP.format(maximum=offering.maximum_shares, cap=offering.cap_shares)
        )


@transaction.atomic
def transition_offering(offering: Offering, method: str, **kwargs) -> Offering:
    if method == "approve":
        _check_bounds(offering)
    getattr(offering, method)(**kwargs)
    message = ISSUER_NOTIFICATIONS.get(method)
    if message:
        title, body = message
        company = offering.token.company
        send_push_notification.defer(
            user_id=str(company.owner_id),
            title=title,
            body=body.format(name=offering.token.name, reason=kwargs.get("reason", "")),
            data={
                "type": "offering",
                "event": method,
                "offering_id": str(offering.uuid),
                "status": offering.status,
            },
            notification_type="general",
        )
    return offering


def _check_not_already_live(offering: Offering) -> None:
    other = Offering.objects.for_token(offering.token).live().exclude(pk=offering.pk).order_by("-created_at").first()
    if other is None:
        return
    raise OfferingRefusedException(
        ALREADY_LIVE.format(
            symbol=offering.token.symbol,
            status=other.get_status_display().lower(),
            opens=other.opens_at.date().isoformat(),
        )
    )


def _check_rails(offering: Offering) -> None:
    assets = list(offering.settlement_assets.all())
    if not offering.accepts_bank_transfer and not assets:
        raise OfferingRefusedException(NO_PAYMENT_RAIL)
    for asset in assets:
        require_deployment(asset)


def _check_exemption(offering: Offering) -> None:
    from offerings.models import OfferingExemption

    if offering.exemption != OfferingExemption.MINIMUM_AMOUNT:
        return
    amount = Decimal(offering.minimum_shares) * offering.price_per_share
    if amount < PRODUCT_VALUE_THRESHOLD_AUD:
        raise OfferingRefusedException(
            MINIMUM_BELOW_THRESHOLD.format(
                threshold=PRODUCT_VALUE_THRESHOLD_AUD,
                shares=offering.minimum_shares,
                price=offering.price_per_share,
                amount=amount,
            )
        )


@transaction.atomic
def submit_offering(offering: Offering, submitted_by) -> Offering:
    token = ShareToken.objects.select_for_update().get(pk=offering.token_id)
    offering.token = token
    company = token.company
    if not token.is_deployed:
        raise OfferingRefusedException(TOKEN_NOT_DEPLOYED.format(symbol=token.symbol))
    if not company.can_issue_tokens:
        raise OfferingRefusedException(
            COMPANY_NOT_ACTIVE.format(name=company.name, status=company.get_status_display().lower())
        )
    _check_not_already_live(offering)
    _check_bounds(offering)
    _check_rails(offering)
    _check_exemption(offering)

    transition_offering(offering, "submit", submitted_by=submitted_by)
    logger.info(f"Offering submitted for {token.symbol} ({company.acn})")
    return offering
