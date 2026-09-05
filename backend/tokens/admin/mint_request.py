from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from shared.utils.admin_display import action_buttons
from tokens.models import MintRequest, MintRequestStatus
from tokens.services import mint_service

from ._helpers import status_badge

REJECT = ("Reject", "reject", "#dc3545")
STATUS_ACTIONS = {
    MintRequestStatus.PENDING: [("Execute Mint", "execute", "#28a745"), REJECT],
    MintRequestStatus.FAILED: [("Retry", "execute", "#fd7e14"), REJECT],
    MintRequestStatus.EXECUTED: [("Executed", None, "#28a745")],
    MintRequestStatus.REJECTED: [("Rejected", None, "#6c757d")],
}


class ExecuteMintForm(forms.Form):
    confirm = forms.BooleanField(required=True, label="I confirm the deposit has been verified")
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Additional Notes (Optional)"
    )


class RejectMintForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=True, label="Rejection Reason")


@admin.register(MintRequest)
class MintRequestAdmin(admin.ModelAdmin):
    list_display = [
        "recipient_name",
        "token_symbol",
        "amount_display",
        "status_badge",
        "deposit_reference",
        "requested_by",
        "created_at",
    ]
    list_filter = ["status", "settlement_asset", "yield_token"]
    search_fields = ["recipient_name", "recipient_address", "deposit_reference", "requested_by__email"]
    readonly_fields = [
        "uuid",
        "settlement_asset",
        "yield_token",
        "recipient_address",
        "recipient_name",
        "amount",
        "deposit_reference",
        "deposit_date",
        "status",
        "requested_by",
        "executed_by",
        "executed_at",
        "transaction",
        "error_message",
        "rejection_reason",
        "created_at",
        "updated_at",
        "status_actions",
        "tx_link",
    ]
    ordering = ["-created_at"]
    status_badge = status_badge(
        {
            MintRequestStatus.PENDING: "#17a2b8",
            MintRequestStatus.APPROVED: "#007bff",
            MintRequestStatus.EXECUTED: "#28a745",
            MintRequestStatus.FAILED: "#dc3545",
            MintRequestStatus.REJECTED: "#6c757d",
        }
    )

    fieldsets = [
        ("Request Information", {"fields": ["uuid", "settlement_asset", "yield_token", "status", "status_actions"]}),
        ("Recipient Details", {"fields": ["recipient_name", "recipient_address", "amount"]}),
        ("Deposit Information", {"fields": ["deposit_reference", "deposit_date"]}),
        ("Notes", {"fields": ["notes"]}),
        ("Processing", {"fields": ["requested_by", "executed_by", "executed_at"]}),
        ("Blockchain", {"fields": ["transaction", "tx_link"], "classes": ["collapse"]}),
        ("Errors", {"fields": ["error_message", "rejection_reason"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:uuid>/execute/",
                self.admin_site.admin_view(self.execute_view),
                name="tokens_mintrequest_execute",
            ),
            path(
                "<uuid:uuid>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="tokens_mintrequest_reject",
            ),
        ]
        return custom_urls + super().get_urls()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Token")
    def token_symbol(self, obj):
        return obj.token.symbol if obj.token else "-"

    @admin.display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        return obj.amount_display

    @admin.display(description="Transaction Hash")
    def tx_link(self, obj):
        if obj.transaction and obj.transaction.tx_hash:
            return format_html('<code style="font-size: 12px;">{}</code>', obj.transaction.tx_hash)
        return "-"

    @admin.display(description="Quick Actions")
    def status_actions(self, obj):
        if obj.pk is None:
            return "-"
        return action_buttons(
            [
                (label, action and reverse(f"admin:tokens_mintrequest_{action}", args=[obj.uuid]), *colors)
                for label, action, *colors in STATUS_ACTIONS.get(obj.status, [])
            ]
        )

    def _refuse(self, request, mint_request, verb):
        messages.error(request, f"Cannot {verb}: request status is '{mint_request.get_status_display()}'")
        return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))

    def _render(self, request, mint_request, action, form):
        context = {
            **self.admin_site.each_context(request),
            "title": f"{action} Mint: {mint_request.recipient_name}",
            "subtitle": None,
            "mint_request": mint_request,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, f"admin/tokens/mintrequest/{action.lower()}_form.html", context)

    def execute_view(self, request, uuid):
        mint_request = get_object_or_404(MintRequest, uuid=uuid)
        if not mint_request.can_be_executed:
            return self._refuse(request, mint_request, "execute")

        form = ExecuteMintForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                tx_hash, _ = mint_service.execute(mint_request, request.user, notes=form.cleaned_data["notes"])
                messages.success(
                    request,
                    f"Successfully minted {mint_request.amount_display} {mint_request.token.symbol} "
                    f"to {mint_request.recipient_name} (tx: {tx_hash[:16]}...)",
                )
            except Exception as exc:
                messages.error(request, f"Mint execution failed: {exc}")
            return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))
        return self._render(request, mint_request, "Execute", form)

    def reject_view(self, request, uuid):
        mint_request = get_object_or_404(MintRequest, uuid=uuid)
        if not mint_request.can_be_rejected:
            return self._refuse(request, mint_request, "reject")

        form = RejectMintForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            mint_request.mark_rejected(user=request.user, reason=form.cleaned_data["reason"])
            messages.warning(request, f"Mint request rejected for {mint_request.recipient_name}")
            return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))
        return self._render(request, mint_request, "Reject", form)
