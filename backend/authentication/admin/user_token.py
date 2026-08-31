from django.contrib import admin

from authentication.models.user_token import UserToken


@admin.register(UserToken)
class UserTokenAdmin(admin.ModelAdmin):
    list_display = (
        "user_email",
        "is_active",
        "is_expired_display",
        "ip_address",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
    )
    list_filter = ("is_active", "created_at", "expires_at", "revoked_at")
    search_fields = ("user__email", "ip_address", "user_agent")
    readonly_fields = (
        "user",
        "access_token",
        "refresh_token",
        "expires_at",
        "is_active",
        "ip_address",
        "user_agent",
        "device_info",
        "last_used_at",
        "revoked_at",
        "created_at",
        "updated_at",
        "is_expired_display",
    )
    fieldsets = (
        ("User Information", {"fields": ("user",)}),
        (
            "Token Information",
            {"fields": ("access_token", "refresh_token", "expires_at", "is_active", "is_expired_display")},
        ),
        ("Device Information", {"fields": ("ip_address", "user_agent", "device_info")}),
        ("Timestamps", {"fields": ("last_used_at", "revoked_at", "created_at", "updated_at")}),
    )

    def user_email(self, obj):
        return obj.user.email

    user_email.short_description = "User Email"
    user_email.admin_order_field = "user__email"

    def is_expired_display(self, obj):
        return obj.is_expired

    is_expired_display.boolean = True
    is_expired_display.short_description = "Is Expired"

    actions = ["revoke_tokens"]

    def revoke_tokens(self, request, queryset):
        for token in queryset:
            token.revoke()
        self.message_user(request, f"{queryset.count()} tokens have been revoked.")

    revoke_tokens.short_description = "Revoke selected tokens"

    def has_add_permission(self, request):
        return False
