from django.contrib import admin

from users.models.user_preferences import UserPreferences


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ("uuid", "user_profile", "selected_account", "selected_portfolio", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = (
        "user_profile__user__email",
        "user_profile__full_name",
        "selected_account__account_number",
        "selected_portfolio__name",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")
    list_select_related = ("user_profile__user", "selected_account", "selected_portfolio")
