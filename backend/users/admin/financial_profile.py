"""
Admin configuration for financial profile.

AML/CTF Compliance:
Admin interface for managing customer source of funds, occupation, and intended use
as required by LEDOVA AML/CTF Program (Part B, Section 16.1, Step 4).
"""

from django.contrib import admin

from users.models.financial_profile import FinancialProfile


@admin.register(FinancialProfile)
class FinancialProfileAdmin(admin.ModelAdmin):
    """Admin for financial profile."""

    list_display = ("uuid", "user_profile", "occupation", "intended_use", "created_at", "updated_at")
    list_filter = ("intended_use", "created_at")
    search_fields = ("user_profile__user__email", "user_profile__full_name", "occupation")
    readonly_fields = ("uuid", "created_at", "updated_at")

    fieldsets = (
        ("User Information", {"fields": ("user_profile",)}),
        (
            "AML/CTF Financial Profile",
            {
                "fields": (
                    "occupation",
                    "source_of_funds",
                    "source_of_funds_other_text",
                    "intended_use",
                    "intended_use_other_text",
                ),
                "description": "AML/CTF compliance information (LEDOVA Section 16.1, Step 4)",
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
        """Get the queryset for the admin view."""
        return super().get_queryset(request).select_related("user_profile__user")
