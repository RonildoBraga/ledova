"""
Admin configuration for device tokens.
"""

from django.contrib import admin

from users.models.device_token import DeviceToken


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    """Admin for device push tokens."""

    list_display = (
        "uuid",
        "user",
        "device_type",
        "is_active",
        "last_used_at",
        "created_at",
    )
    list_filter = ("device_type", "is_active", "created_at", "last_used_at")
    search_fields = (
        "user__email",
        "push_token",
    )
    readonly_fields = ("uuid", "created_at", "updated_at", "last_used_at")
    list_select_related = ("user",)

    fieldsets = (
        (
            "User Information",
            {
                "fields": ("user",),
            },
        ),
        (
            "Token Details",
            {
                "fields": (
                    "push_token",
                    "device_type",
                    "is_active",
                ),
            },
        ),
        (
            "System Information",
            {
                "fields": ("uuid", "last_used_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["deactivate_tokens", "activate_tokens"]

    @admin.action(description="Deactivate selected tokens")
    def deactivate_tokens(self, request, queryset):
        """Deactivate selected device tokens."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} token(s) deactivated.")

    @admin.action(description="Activate selected tokens")
    def activate_tokens(self, request, queryset):
        """Activate selected device tokens."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} token(s) activated.")
