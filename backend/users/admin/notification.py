"""
Admin configuration for Notification model.
"""

from django.contrib import admin

from users.models.notification import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "title",
        "notification_type",
        "get_user_email",
        "is_read",
        "is_archived",
        "created_at",
    )
    list_display_links = ("uuid", "title")
    search_fields = (
        "title",
        "body",
        "user__email",
    )
    list_filter = (
        "notification_type",
        "is_read",
        "is_archived",
        "created_at",
    )
    readonly_fields = ("uuid", "created_at", "updated_at", "read_at")
    ordering = ("-created_at",)
    list_per_page = 25
    fieldsets = (
        (None, {"fields": ("uuid", "user", "title", "body", "notification_type", "data")}),
        (
            "Status",
            {"fields": ("is_read", "read_at", "is_archived")},
        ),
        (
            "System Information",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_user_email(self, obj):
        return obj.user.email

    get_user_email.short_description = "User"
    get_user_email.admin_order_field = "user__email"
