from django.contrib import admin

from compliance.admin._helpers import GREEN, ORANGE, RED, YELLOW, choice_badge
from compliance.models import CustomerRiskAssessment

ASSESSMENT_STATUS_COLOURS = {"pending": YELLOW, "complete": GREEN, "incomplete": RED}
RISK_RATING_COLOURS = {"low": GREEN, "medium": YELLOW, "high": ORANGE, "extreme": RED}
PEP_COLOURS = {"domestic": ORANGE, "foreign": RED, "international_org": RED, "family": RED, "associate": RED}


@admin.register(CustomerRiskAssessment)
class CustomerRiskAssessmentAdmin(admin.ModelAdmin):
    list_display = [
        "user_account",
        "status_badge",
        "risk_rating_badge",
        "customer_risk_score",
        "geographic_risk_score",
        "pep_badge",
        "is_automated",
        "valid_from",
        "next_review_date",
        "created_at",
    ]
    list_filter = [
        "assessment_status",
        "overall_risk_rating",
        "pep_type",
        "high_risk_country",
        "high_risk_occupation",
        "is_automated",
    ]
    search_fields = ["user_account__account_number", "user_account__uuid", "assessment_reason"]
    readonly_fields = ["uuid", "created_at", "updated_at", "total_score"]
    ordering = ["-created_at"]

    @admin.display(description="Status", ordering="assessment_status")
    def status_badge(self, obj):
        return choice_badge(obj.assessment_status, ASSESSMENT_STATUS_COLOURS)

    @admin.display(description="Risk Rating", ordering="overall_risk_rating")
    def risk_rating_badge(self, obj):
        return choice_badge(obj.overall_risk_rating, RISK_RATING_COLOURS)

    @admin.display(description="PEP", ordering="pep_type")
    def pep_badge(self, obj):
        return choice_badge(obj.pep_type if obj.is_pep else None, PEP_COLOURS)

    @admin.display(description="Total Score")
    def total_score(self, obj):
        return "-" if obj.total_risk_score is None else f"{obj.total_risk_score}/15"
