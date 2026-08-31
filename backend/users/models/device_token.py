"""
Device token model for push notifications.
"""

from django.conf import settings
from django.db import models

from shared.models import BaseModel


class DeviceToken(BaseModel):
    """
    Stores device push tokens for notifications.

    Each token represents a device that can receive push notifications.
    Tokens are provided by Expo Push Notification service and follow
    the format: ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]
    """

    class DeviceType(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
        help_text="User who owns this device",
    )
    push_token = models.CharField(
        max_length=255,
        unique=True,
        help_text="Expo push token (e.g., ExponentPushToken[xxx])",
    )
    device_type = models.CharField(
        max_length=10,
        choices=DeviceType.choices,
        help_text="Device platform (iOS or Android)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this token is active and can receive notifications",
    )
    last_used_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time this token was used to send a notification",
    )

    class Meta:
        db_table = "users_device_token"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["push_token"]),
        ]
        verbose_name = "Device Token"
        verbose_name_plural = "Device Tokens"

    def __str__(self):
        return f"{self.user.email} - {self.device_type} ({self.push_token[:30]}...)"

    @classmethod
    def validate_expo_token(cls, token: str) -> bool:
        """
        Validate that a token follows the Expo push token format.

        Expo tokens should start with 'ExponentPushToken[' and end with ']'.
        """
        return token.startswith("ExponentPushToken[") and token.endswith("]")
