from django.conf import settings
from django.db import models

from shared.models import BaseModel
from users.models.owner_column import DerivesOwnerFromProfile
from users.querysets.notification_preferences import NotificationPreferencesQuerySet


class NotificationPreferences(DerivesOwnerFromProfile, BaseModel):
    objects = NotificationPreferencesQuerySet.as_manager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
        help_text="Owner, derived from user_profile.user and held directly so a row-level security policy can read it",
    )

    user_profile = models.OneToOneField(
        "users.UserProfile",
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        help_text="User profile these preferences belong to",
    )
    transaction_alerts = models.BooleanField(
        default=True,
        help_text="Notifications for transaction status changes",
    )
    price_alerts = models.BooleanField(
        default=False,
        help_text="Notifications for price threshold alerts",
    )
    marketing = models.BooleanField(
        default=False,
        help_text="Marketing and promotional notifications",
    )

    class Meta:
        db_table = "users_notification_preferences"
        verbose_name = "Notification Preferences"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"NotificationPreferences for {self.user_profile}"

    def can_receive_notification(self, notification_type: str) -> bool:
        type_mapping = {
            "transaction": self.transaction_alerts,
            "price": self.price_alerts,
            "marketing": self.marketing,
            "general": True,
        }

        return type_mapping.get(notification_type, True)
