import logging
from typing import Any, Dict, Optional

from procrastinate import RetryStrategy

from authentication.models import CustomUser
from ledova_backend.procrastinate_app import app
from shared.db import acting_for
from users.services.notifications import NotificationService

logger = logging.getLogger(__name__)

NO_RECIPIENT = {"status": "error", "error": "Recipient required"}


@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    notification_type: str = "general",
) -> Dict[str, Any]:
    if user_id is None:
        logger.error("[NOTIFICATION_TASK] Refused a push with no recipient")
        return dict(NO_RECIPIENT)
    with acting_for(user_id):
        return _send_push_notification(user_id, title, body, data, notification_type)


def _send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]],
    notification_type: str,
) -> Dict[str, Any]:
    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        logger.error(f"[NOTIFICATION_TASK] User not found: {user_id}")
        return {"status": "error", "error": "User not found"}

    service = NotificationService()
    result = service.notify_user(
        user=user,
        title=title,
        body=body,
        data=data,
        notification_type=notification_type,
    )

    logger.info(f"[NOTIFICATION_TASK] Sent notification to user {user_id}: {result['status']}")
    return result


@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def send_transaction_notification(
    user_id: str,
    transaction_id: str,
    event_type: str,
) -> Dict[str, Any]:
    if user_id is None:
        logger.error("[NOTIFICATION_TASK] Refused a transaction notice with no recipient")
        return dict(NO_RECIPIENT)
    with acting_for(user_id):
        return _send_transaction_notification(user_id, transaction_id, event_type)


def _send_transaction_notification(user_id: str, transaction_id: str, event_type: str) -> Dict[str, Any]:
    from wallets.models import Transaction

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        logger.error(f"[NOTIFICATION_TASK] User not found: {user_id}")
        return {"status": "error", "error": "User not found"}

    try:
        transaction = Transaction.objects.select_related("asset").get(pk=transaction_id)
    except Transaction.DoesNotExist:
        logger.error(f"[NOTIFICATION_TASK] Transaction not found: {transaction_id}")
        return {"status": "error", "error": "Transaction not found"}

    service = NotificationService()
    result = service.notify_transaction(
        user=user,
        transaction=transaction,
        event_type=event_type,
    )

    logger.info(
        f"[NOTIFICATION_TASK] Sent transaction notification to user {user_id}: {event_type} - {result['status']}"
    )
    return result
