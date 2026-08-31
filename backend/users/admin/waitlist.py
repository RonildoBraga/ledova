"""
Admin configuration for waitlist entries.
"""

from django.contrib import admin
from django.utils.html import format_html

from users.models.waitlist import Waitlist


@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    """Admin for waitlist entries."""

    list_display = ("email", "subscribed_at", "is_active", "status_badge")
    list_filter = ("is_active", "subscribed_at")
    search_fields = ("email",)
    readonly_fields = ("uuid", "subscribed_at", "created_at", "updated_at")
    ordering = ("-subscribed_at",)

    fieldsets = (
        ("Waitlist Information", {"fields": ("email", "is_active")}),
        (
            "System Information",
            {
                "fields": ("uuid", "subscribed_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def status_badge(self, obj):
        """Display a colored status badge."""
        if obj.is_active:
            color = "#28a745"  # Green
            text = "Active"
        else:
            color = "#dc3545"  # Red
            text = "Inactive"

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 12px; font-weight: bold;">{}</span>',
            color,
            text,
        )

    status_badge.short_description = "Status"

    def get_queryset(self, request):
        """Optimize queryset for better performance."""
        return super().get_queryset(request).order_by("-subscribed_at")

    actions = ["mark_active", "mark_inactive"]

    def mark_active(self, request, queryset):
        """Mark selected waitlist entries as active."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} waitlist entries marked as active.")

    mark_active.short_description = "Mark selected entries as active"

    def mark_inactive(self, request, queryset):
        """Mark selected waitlist entries as inactive."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} waitlist entries marked as inactive.")

    mark_inactive.short_description = "Mark selected entries as inactive"
