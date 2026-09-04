from django.contrib import admin

from users.models.device_token import DeviceToken


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("uuid", "user", "device_type", "is_active", "last_used_at", "created_at")
    list_filter = ("device_type", "is_active", "created_at", "last_used_at")
    search_fields = ("user__email", "push_token")
    readonly_fields = ("uuid", "created_at", "updated_at", "last_used_at")
    list_select_related = ("user",)
    actions = ["deactivate_tokens", "activate_tokens"]

    @admin.action(description="Deactivate selected tokens")
    def deactivate_tokens(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} token(s) deactivated.")

    @admin.action(description="Activate selected tokens")
    def activate_tokens(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} token(s) activated.")
