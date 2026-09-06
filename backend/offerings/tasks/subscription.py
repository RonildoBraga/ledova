import logging

from django.contrib.auth import get_user_model
from django.utils import timezone
from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from offerings.models import Subscription
from offerings.services.subscription import executed_requests_pending_allotment
from tokens.exceptions import (
    InvalidRecipientAddressException,
    InvalidTokenStateException,
    IssuanceRefusedException,
)
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)

SUBSCRIPTION_NOT_FOUND = "Subscription not found"
NO_ISSUANCE_REQUEST = "Subscription has no issuance request to execute"
EXPIRY_NOTE = "Payment was not received by {due}; the subscription lapsed."


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def allot_subscription_task(subscription_uuid: str, executed_by: int | None = None):
    subscription = (
        Subscription.objects.filter(uuid=subscription_uuid)
        .select_related("issuance_request", "issuance_request__token", "issuance_request__token__company")
        .first()
    )
    if subscription is None:
        logger.error(f"Subscription not found: {subscription_uuid}")
        return {"success": False, "error": SUBSCRIPTION_NOT_FOUND}
    request = subscription.issuance_request
    if request is None:
        logger.error(f"Subscription {subscription_uuid} has no issuance request")
        return {"success": False, "error": NO_ISSUANCE_REQUEST}

    user = get_user_model().objects.filter(pk=executed_by).first() if executed_by else None
    try:
        result = ShareTokenService().execute_request(request, executed_by=user)
    except (InvalidRecipientAddressException, InvalidTokenStateException, IssuanceRefusedException) as exc:
        logger.warning(f"Subscription {subscription_uuid} not allotted: {exc.detail}")
        return {"success": False, "error": str(exc.detail)}

    subscription.refresh_from_db(fields=["status"])
    _mirror_allotted(subscription)
    return {"success": True, **result}


def _mirror_allotted(subscription: Subscription) -> bool:
    from offerings.models import SubscriptionStatus

    if subscription.status != SubscriptionStatus.PAID:
        return False
    subscription.mark_allotted()
    return True


@app.periodic(cron="*/5 * * * *")
@app.task
def reconcile_subscriptions(timestamp: int = 0):
    flipped = 0
    for subscription in executed_requests_pending_allotment():
        if _mirror_allotted(subscription):
            flipped += 1
            logger.info(f"Subscription {subscription.uuid} mirrored to allotted from an executed request")
    logger.info(f"Subscriptions reconciled: flipped={flipped}")
    return {"flipped": flipped}


@app.periodic(cron="0 3 * * *")
@app.task
def expire_unpaid_subscriptions(timestamp: int = 0):
    now = timezone.now()
    expired = 0
    for subscription in Subscription.objects.unpaid_past_due(now):
        subscription.reject(notes=EXPIRY_NOTE.format(due=subscription.payment_due_at.isoformat()))
        expired += 1
    logger.info(f"Unpaid subscriptions expired: {expired}")
    return {"expired": expired}
