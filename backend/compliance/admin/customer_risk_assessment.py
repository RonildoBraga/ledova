from django.contrib import admin
from django.utils.html import format_html

from compliance.models import CustomerRiskAssessment


@admin.register(CustomerRiskAssessment)
class CustomerRiskAssessmentAdmin(admin.ModelAdmin):
    """
    Admin for customer risk assessments.

    Allows AML Compliance Officer to:
    - View customer risk ratings and component scores
    - Review assessment reasons and risk factors
    - Track assessment validity and review dates
    - Perform manual assessments when needed
    """

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
    search_fields = [
        "user_account__account_number",
        "user_account__uuid",
        "assessment_reason",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "total_risk_score",
    ]
    ordering = ["-created_at"]

    fieldsets = (
        (
            "User Account",
            {
                "fields": ("user_account",),
            },
        ),
        (
            "Assessment Status",
            {
                "fields": ("assessment_status",),
            },
        ),
        (
            "Risk Rating",
            {
                "fields": (
                    "overall_risk_rating",
                    "customer_risk_score",
                    "geographic_risk_score",
                    "product_risk_score",
                    "total_risk_score",
                ),
            },
        ),
        (
            "Risk Factors",
            {
                "fields": (
                    "pep_type",
                    "pep_details",
                    "high_risk_country",
                    "high_risk_occupation",
                ),
            },
        ),
        (
            "Assessment Details",
            {
                "fields": (
                    "assessment_reason",
                    "assessed_by",
                    "is_automated",
                ),
            },
        ),
        (
            "Validity Period",
            {
                "fields": (
                    "valid_from",
                    "valid_until",
                    "next_review_date",
                ),
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

    def status_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "complete": "#28a745",
            "incomplete": "#dc3545",
        }
        color = colors.get(obj.assessment_status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.assessment_status.upper(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "assessment_status"

    def risk_rating_badge(self, obj):
        if not obj.overall_risk_rating:
            return "-"
        colors = {
            "low": "#28a745",
            "medium": "#ffc107",
            "high": "#fd7e14",
            "extreme": "#dc3545",
        }
        color = colors.get(obj.overall_risk_rating, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.overall_risk_rating.upper(),
        )

    risk_rating_badge.short_description = "Risk Rating"
    risk_rating_badge.admin_order_field = "overall_risk_rating"

    def pep_badge(self, obj):
        if obj.is_pep:
            colors = {
                "domestic": "#fd7e14",
                "foreign": "#dc3545",
                "international_org": "#dc3545",
                "family": "#dc3545",
                "associate": "#dc3545",
            }
            color = colors.get(obj.pep_type, "#dc3545")
            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">{}</span>',
                color,
                obj.pep_type.upper().replace("_", " "),
            )
        return "-"

    pep_badge.short_description = "PEP"
    pep_badge.admin_order_field = "pep_type"

    def total_risk_score(self, obj):
        score = obj.total_risk_score
        return f"{score}/15" if score is not None else "-"

    total_risk_score.short_description = "Total Score"
