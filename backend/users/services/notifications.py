import logging
from typing import Any, Dict, Optional

from integrations.expo_push import ExpoPushClient, ExpoPushError
from users.models import DeviceToken, Notification, NotificationPreferences

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.expo_client = ExpoPushClient()

    def notify_user(
        self,
        user,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_type: str = "general",
    ) -> Dict[str, Any]:
        # Always create an in-app notification record regardless of push preferences
        Notification.objects.create(
            user=user,
            title=title,
            body=body,
            notification_type=notification_type,
            data=data or {},
        )

        try:
            prefs = NotificationPreferences.objects.get(user_profile=user.userprofile)
            if not prefs.can_receive_notification(notification_type):
                logger.info(f"Skipped for user {user.email}: {notification_type} notifications disabled")
                return {
                    "status": "skipped",
                    "reason": f"{notification_type} notifications disabled",
                    "sent": 0,
                    "failed": 0,
                }
        except NotificationPreferences.DoesNotExist:
            pass

        device_tokens = list(DeviceToken.objects.filter(user=user, is_active=True))

        if not device_tokens:
            logger.info(f"No active devices for user {user.email}")
            return {
                "status": "no_devices",
                "sent": 0,
                "failed": 0,
            }

        messages = []
        for token in device_tokens:
            messages.append(
                {
                    "to": token.push_token,
                    "title": title,
                    "body": body,
                    "data": data or {},
                    "sound": "default",
                }
            )

        try:
            results = self.expo_client.send_batch(messages)

            sent = sum(1 for r in results if r.get("status") == "ok")
            failed = len(results) - sent

            for i, result in enumerate(results):
                if result.get("status") == "error":
                    details = result.get("details", {})
                    error_type = details.get("error")

                    if error_type in ["DeviceNotRegistered", "InvalidCredentials"]:
                        token = device_tokens[i]
                        DeviceToken.objects.filter(pk=token.pk).update(is_active=False)
                        logger.info(f"Deactivated invalid token for {user.email}: {token.push_token[:30]}...")

            logger.info(f"Sent to user {user.email}: {sent} successful, {failed} failed")

            return {
                "status": "sent",
                "sent": sent,
                "failed": failed,
                "results": results,
            }

        except ExpoPushError as e:
            logger.error(f"Failed to send to user {user.email}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "sent": 0,
                "failed": len(messages),
            }

    def notify_transaction(
        self,
        user,
        transaction,
        event_type: str,
    ) -> Dict[str, Any]:
        event_messages = {
            "confirmed": {
                "title": "Transaction Confirmed",
                "body": f"Your transaction of {transaction.amount} {transaction.asset.symbol} has been confirmed.",
            },
            "failed": {
                "title": "Transaction Failed",
                "body": f"Your transaction of {transaction.amount} {transaction.asset.symbol} has failed.",
            },
            "pending": {
                "title": "Transaction Pending",
                "body": f"Your transaction of {transaction.amount} {transaction.asset.symbol} is being processed.",
            },
        }

        message = event_messages.get(
            event_type,
            {
                "title": "Transaction Update",
                "body": "Your transaction has been updated.",
            },
        )

        data = {
            "type": "transaction",
            "event": event_type,
            "transaction_id": str(transaction.uuid),
        }

        return self.notify_user(
            user=user,
            title=message["title"],
            body=message["body"],
            data=data,
            notification_type="transaction",
        )
