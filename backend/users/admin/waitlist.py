from django.contrib import admin

from users.models.waitlist import Waitlist


@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ("email", "subscribed_at", "is_active")
    list_filter = ("is_active", "subscribed_at")
    search_fields = ("email",)
    readonly_fields = ("uuid", "subscribed_at", "created_at", "updated_at")
    ordering = ("-subscribed_at",)
    actions = ["mark_active", "mark_inactive"]

    @admin.action(description="Mark selected entries as active")
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} waitlist entries marked as active.")

    @admin.action(description="Mark selected entries as inactive")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} waitlist entries marked as inactive.")
