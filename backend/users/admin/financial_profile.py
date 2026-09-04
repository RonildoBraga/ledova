"""Source of funds, occupation and intended use: LEDOVA AML/CTF Program Part B, Section 16.1, Step 4."""

from django.contrib import admin

from users.models.financial_profile import FinancialProfile


@admin.register(FinancialProfile)
class FinancialProfileAdmin(admin.ModelAdmin):
    list_display = ("uuid", "user_profile", "occupation", "intended_use", "created_at", "updated_at")
    list_filter = ("intended_use", "created_at")
    search_fields = ("user_profile__user__email", "user_profile__full_name", "occupation")
    readonly_fields = ("uuid", "created_at", "updated_at")
    list_select_related = ("user_profile__user",)
