from django.contrib import admin

from tokens.models import CapitalIncreaseRequest, RequestStatus

from .review_workflow import ReviewWorkflowAdmin


@admin.register(CapitalIncreaseRequest)
class CapitalIncreaseAdmin(ReviewWorkflowAdmin):
    label = "Capital increase"
    deletable_status = RequestStatus.DRAFT
    list_display = [
        "token_symbol",
        "additional_shares",
        "new_authorized_total",
        "status_badge",
        "dilution_display",
        "submitted_by",
        "submitted_at",
        "created_at",
    ]
    list_filter = ["status", "token__company"]
    search_fields = ["token__symbol", "token__name", "purpose", "submitted_by__email"]
    detail_fieldset = (
        "Capital Increase Details",
        {
            "fields": [
                "additional_shares",
                "new_authorized_total",
                "purpose",
                "board_resolution_reference",
                "shareholder_approval_reference",
                "dilution_percentage",
            ]
        },
    )

    def describe(self, obj):
        return f"+{obj.additional_shares} shares"

    def detail_rows(self, obj):
        return [
            ("Additional Shares", f"+{obj.additional_shares} shares"),
            ("New Authorized Total", f"{obj.new_authorized_total} shares"),
            ("Purpose", obj.purpose),
            ("Board Resolution", obj.board_resolution_reference),
            ("Shareholder Approval", obj.shareholder_approval_reference or "-"),
        ]

    def execution_steps(self, obj):
        return [f"setAuthorizedShares({obj.new_authorized_total}) - Raise the authorized share cap; nothing is minted"]
