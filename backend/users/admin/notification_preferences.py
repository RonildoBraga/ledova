"""
Admin configuration for notification preferences.
"""

from django.contrib import admin

from users.models.notification_preferences import NotificationPreferences


@admin.register(NotificationPreferences)
class NotificationPreferencesAdmin(admin.ModelAdmin):
    """Admin for user notification preferences."""

    list_display = (
        "uuid",
        "user_profile",
        "transaction_alerts",
        "price_alerts",
        "marketing",
        "updated_at",
    )
    list_filter = (
        "transaction_alerts",
        "price_alerts",
        "marketing",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "user_profile__user__email",
        "user_profile__full_name",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")
    list_select_related = ("user_profile", "user_profile__user")

    fieldsets = (
        (
            "User Information",
            {
                "fields": ("user_profile",),
            },
        ),
        (
            "Notification Settings",
            {
                "fields": (
                    "transaction_alerts",
                    "price_alerts",
                    "marketing",
                ),
                "description": "Configure which notifications the user receives.",
            },
        ),
        (
            "System Information",
            {
                "fields": ("uuid", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["enable_all_notifications", "disable_all_notifications"]

    @admin.action(description="Enable all notifications for selected users")
    def enable_all_notifications(self, request, queryset):
        """Enable all notification types."""
        count = queryset.update(
            transaction_alerts=True,
            price_alerts=True,
            marketing=True,
        )
        self.message_user(request, f"All notifications enabled for {count} user(s).")

    @admin.action(description="Disable all notifications for selected users")
    def disable_all_notifications(self, request, queryset):
        """Disable all notification types."""
        count = queryset.update(
            transaction_alerts=False,
            price_alerts=False,
            marketing=False,
        )
        self.message_user(request, f"All notifications disabled for {count} user(s).")
