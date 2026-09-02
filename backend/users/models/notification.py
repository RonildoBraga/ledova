from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from users.querysets.notification import NotificationQuerySet


class NotificationType(models.TextChoices):
    TRANSACTION = "transaction", "Transaction"
    PRICE = "price", "Price"
    MARKETING = "marketing", "Marketing"
    GENERAL = "general", "General"
    SYSTEM = "system", "System"


class Notification(BaseModel):
    """Persisted for every NotificationService send, regardless of push preferences."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="The user this notification belongs to",
    )
    title = models.CharField(
        max_length=255,
        help_text="Notification title",
    )
    body = models.TextField(
        help_text="Notification body text",
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
        help_text="Category of the notification",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured data for the notification",
    )
    is_read = models.BooleanField(
        default=False,
        help_text="Whether the notification has been read",
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was read",
    )
    is_archived = models.BooleanField(
        default=False,
        help_text="Whether the notification has been archived",
    )

    objects = NotificationQuerySet.as_manager()

    class Meta:
        db_table = "notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_notification_user_created"),
            models.Index(fields=["user", "is_read"], name="idx_notification_user_read"),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.email}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])
