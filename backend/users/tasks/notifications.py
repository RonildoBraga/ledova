import logging
from typing import Any, Dict, Optional

from procrastinate import RetryStrategy

from authentication.models import CustomUser
from ledova_backend.procrastinate_app import app
from users.services.notifications import NotificationService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    notification_type: str = "general",
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

    logger.info(f"[NOTIFICATION_TASK] Sent notification to {user.email}: {result['status']}")
    return result


@app.task(retry=RetryStrategy(max_attempts=4, wait=60))
def send_transaction_notification(
    user_id: str,
    transaction_id: str,
    event_type: str,
) -> Dict[str, Any]:
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

    logger.info(f"[NOTIFICATION_TASK] Sent transaction notification to {user.email}: {event_type} - {result['status']}")
    return result
