from django.contrib import admin

from tokens.models import RequestStatus, ShareIssuanceRequest

from ._helpers import short_hex
from .review_workflow import ReviewWorkflowAdmin


@admin.register(ShareIssuanceRequest)
class ShareIssuanceRequestAdmin(ReviewWorkflowAdmin):
    label = "Issuance"
    deletable_status = RequestStatus.SUBMITTED
    list_display = [
        "token_symbol",
        "recipient_display",
        "amount",
        "issuance_type",
        "status_badge",
        "dilution_display",
        "submitted_by",
        "submitted_at",
        "created_at",
    ]
    list_filter = ["status", "issuance_type", "token__company"]
    search_fields = [
        "token__symbol",
        "token__name",
        "reason",
        "recipient_address",
        "recipient_name",
        "submitted_by__email",
    ]
    detail_fieldset = (
        "Issuance Details",
        {"fields": ["recipient_address", "recipient_name", "amount", "issuance_type", "reason", "dilution_percentage"]},
    )

    @admin.display(description="Recipient")
    def recipient_display(self, obj):
        address = short_hex(obj.recipient_address)
        return f"{obj.recipient_name} ({address})" if obj.recipient_name else address

    def describe(self, obj):
        return f"{obj.amount} shares to {short_hex(obj.recipient_address)}"

    def detail_rows(self, obj):
        recipient = f"{obj.recipient_name} - {obj.recipient_address}" if obj.recipient_name else obj.recipient_address
        return [
            ("Recipient", recipient),
            ("Amount", f"{obj.amount} shares"),
            ("Issuance Type", obj.get_issuance_type_display()),
            ("Reason", obj.reason),
        ]

    def execution_steps(self, obj):
        return [
            "isWhitelisted(recipient) and authorizedShares() - totalSupply() >= amount - Checked before sending",
            f"mint({obj.recipient_address}, {obj.amount}) - Mint shares to recipient",
        ]
