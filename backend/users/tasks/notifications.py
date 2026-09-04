import logging
from typing import Any, Dict, List, Optional

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


@app.task
def send_batch_notifications(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Send batch notifications. Each message is a dict with user_id/title/body/data/notification_type."""
    total_sent = 0
    total_failed = 0
    results = []

    service = NotificationService()

    for msg in messages:
        user_id = msg.get("user_id")
        if not user_id:
            results.append({"status": "error", "error": "Missing user_id"})
            total_failed += 1
            continue

        try:
            user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            results.append({"user_id": user_id, "status": "error", "error": "User not found"})
            total_failed += 1
            continue

        try:
            result = service.notify_user(
                user=user,
                title=msg.get("title", "Notification"),
                body=msg.get("body", ""),
                data=msg.get("data"),
                notification_type=msg.get("notification_type", "general"),
            )

            total_sent += result.get("sent", 0)
            total_failed += result.get("failed", 0)
            results.append({"user_id": user_id, "result": result})

        except Exception as e:
            logger.error(f"[NOTIFICATION_TASK] Batch notification failed for {user_id}: {e}")
            results.append({"user_id": user_id, "status": "error", "error": str(e)})
            total_failed += 1

    logger.info(f"[NOTIFICATION_TASK] Batch complete: {total_sent} sent, {total_failed} failed")

    return {
        "status": "completed",
        "total_sent": total_sent,
        "total_failed": total_failed,
        "message_count": len(messages),
        "results": results,
    }
