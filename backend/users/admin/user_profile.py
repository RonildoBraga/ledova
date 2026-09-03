from django.contrib import admin

from users.models.financial_profile import FinancialProfile
from users.models.user_profile import UserProfile


class FinancialProfileInline(admin.StackedInline):
    model = FinancialProfile
    extra = 0
    readonly_fields = ("uuid", "created_at", "updated_at")
    can_delete = False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "user",
        "full_name",
        "full_phone_number",
        "email",
        "citizenship_country",
        "date_of_birth",
        "is_id_verified",
        "kyc_provider",
        "review_result",
        "terms_and_conditions",
        "created_at",
    )
    search_fields = ("user__email", "full_name", "phone_country_code", "phone_number", "residential_address")
    list_filter = (
        "is_id_verified",
        "kyc_provider",
        "review_result",
        "terms_and_conditions",
        "created_at",
        "is_signup_completed",
        "confirmed_over_18",
        "confirmed_australian_resident",
        "confirmed_individual_account",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")
    list_select_related = ("user", "citizenship_country")
    inlines = [FinancialProfileInline]

    @admin.display(description="Email", ordering="user__email")
    def email(self, obj):
        return obj.user.email

    @admin.display(description="Full Phone Number")
    def full_phone_number(self, obj):
        if obj.phone_country_code and obj.phone_number:
            return f"{obj.phone_country_code} {obj.phone_number}"
        return obj.phone_number or "-"
