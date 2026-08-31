from django.contrib import admin

from users.models.financial_profile import FinancialProfile
from users.models.user_profile import UserProfile


class FinancialProfileInline(admin.StackedInline):
    model = FinancialProfile
    extra = 0
    readonly_fields = ("uuid", "created_at", "updated_at")
    fields = (
        "occupation",
        "source_of_funds",
        "source_of_funds_other_text",
        "intended_use",
        "intended_use_other_text",
        "uuid",
        "created_at",
        "updated_at",
    )
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
        "pre_screening_status",
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
    readonly_fields = ("uuid", "created_at", "updated_at", "pre_screening_completed_at")
    inlines = [FinancialProfileInline]
    fieldsets = (
        (
            "User Information",
            {
                "fields": (
                    "user",
                    "uuid",
                    "full_name",
                    "phone_country_code",
                    "phone_number",
                    "date_of_birth",
                    "residential_address",
                )
            },
        ),
        (
            "KYC Verification",
            {
                "fields": (
                    "kyc_provider",
                    "verification_status",
                    "review_result",
                    "rejection_labels",
                    "verified_at",
                    "kycaid_applicant_id",
                    "kycaid_verification_id",
                    "sumsub_applicant_id",
                )
            },
        ),
        (
            "Citizenship and Regulatory Information",
            {"fields": ("citizenship_country", "residence_country")},
        ),
        (
            "Pre-Screening / Eligibility (AML/CTF)",
            {
                "fields": (
                    "confirmed_over_18",
                    "confirmed_australian_resident",
                    "confirmed_individual_account",
                    "pre_screening_completed_at",
                )
            },
        ),
        (
            "Verification Status",
            {"fields": ("is_id_verified", "terms_and_conditions", "is_signup_completed")},
        ),
        (
            "System Information",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def email(self, obj):
        return obj.user.email

    email.short_description = "Email"
    email.admin_order_field = "user__email"

    def full_phone_number(self, obj):
        """Display the complete phone number with country code."""
        if obj.phone_country_code and obj.phone_number:
            return f"{obj.phone_country_code} {obj.phone_number}"
        elif obj.phone_number:
            return obj.phone_number
        return "-"

    full_phone_number.short_description = "Full Phone Number"

    def pre_screening_status(self, obj):
        """Display pre-screening completion status."""
        if obj.confirmed_over_18 and obj.confirmed_australian_resident and obj.confirmed_individual_account:
            return "✅ Complete"
        elif any([obj.confirmed_over_18, obj.confirmed_australian_resident, obj.confirmed_individual_account]):
            return "⚠️ Partial"
        return "❌ Not Started"

    pre_screening_status.short_description = "Pre-Screening"

    def save_model(self, request, obj, form, change):
        # Ensures that any superuser-made changes preserve the user profile's status
        super().save_model(request, obj, form, change)
