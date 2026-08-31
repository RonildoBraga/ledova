"""
Admin configuration for user preferences.
"""

from django.contrib import admin

from users.models.user_preferences import UserPreferences


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    """Admin for user preferences."""

    list_display = ("uuid", "user_profile", "selected_account", "selected_portfolio", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = (
        "user_profile__user__email",
        "user_profile__full_name",
        "selected_account__account_number",
        "selected_portfolio__name",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")

    fieldsets = (
        ("User Information", {"fields": ("user_profile",)}),
        (
            "Selected Preferences",
            {
                "fields": (
                    "selected_account",
                    "selected_portfolio",
                ),
                "description": "Note: The selected portfolio must belong to the selected account.",
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

    def get_queryset(self, request):
        """Get the queryset for the admin view with optimized data loading."""
        return super().get_queryset(request).with_optimized_data()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Customize foreign key fields to show relevant choices only."""
        if db_field.name == "selected_account":
            if hasattr(request, "_obj_") and request._obj_:
                user_profile = request._obj_.user_profile
                kwargs["queryset"] = user_profile.user_accounts.all()

        if db_field.name == "selected_portfolio":
            if hasattr(request, "_obj_") and request._obj_:
                user_profile = request._obj_.user_profile
                user_portfolios = []
                for account in user_profile.user_accounts.all():
                    user_portfolios.extend(account.portfolios.all())
                kwargs["queryset"] = user_profile.user_accounts.values_list("portfolios", flat=True)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """Store the object in the request for use in formfield_for_foreignkey."""
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)
