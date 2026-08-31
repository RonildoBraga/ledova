from django.contrib import admin

from users.models import UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = ("uuid", "account_number", "activation_date", "user_profile_count", "created_at")
    search_fields = ("account_number", "user_profiles__user__email", "user_profiles__full_name")
    list_filter = ("activation_date", "created_at")
    readonly_fields = ("uuid", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("uuid", "account_number", "activation_date", "user_profiles")}),
        (
            "System Information",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    filter_horizontal = ("user_profiles",)  # Better UX for ManyToMany

    def user_profile_count(self, obj):
        return obj.user_profiles.count()

    user_profile_count.short_description = "Number of User Profiles"
