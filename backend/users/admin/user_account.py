from django.contrib import admin

from users.models import UserAccount


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = ("uuid", "account_number", "activation_date", "user_profile_count", "created_at")
    search_fields = ("account_number", "user_profiles__user__email", "user_profiles__full_name")
    list_filter = ("activation_date", "created_at")
    readonly_fields = ("uuid", "created_at", "updated_at")
    filter_horizontal = ("user_profiles",)

    @admin.display(description="Number of User Profiles")
    def user_profile_count(self, obj):
        return obj.user_profiles.count()
