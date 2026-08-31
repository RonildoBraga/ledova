import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tokens.models import MintRequest, MintRequestStatus
from tokens.services import StablecoinService, YieldTokenService

logger = logging.getLogger(__name__)


class ExecuteMintForm(forms.Form):

    confirm = forms.BooleanField(
        required=True,
        label="I confirm the deposit has been verified",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Additional Notes (Optional)",
    )


class RetryMintForm(forms.Form):

    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Additional Notes (Optional)",
    )


class RejectMintForm(forms.Form):

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        label="Rejection Reason",
    )


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
    list_filter = ["status", "stablecoin", "yield_token"]
    search_fields = [
        "recipient_name",
        "recipient_address",
        "deposit_reference",
        "requested_by__email",
    ]
    readonly_fields = [
        "uuid",
        "stablecoin",
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

    fieldsets = [
        (
            "Request Information",
            {
                "fields": [
                    "uuid",
                    "stablecoin",
                    "yield_token",
                    "status",
                    "status_actions",
                ],
            },
        ),
        (
            "Recipient Details",
            {
                "fields": [
                    "recipient_name",
                    "recipient_address",
                    "amount",
                ],
            },
        ),
        (
            "Deposit Information",
            {
                "fields": [
                    "deposit_reference",
                    "deposit_date",
                ],
            },
        ),
        (
            "Notes",
            {
                "fields": [
                    "notes",
                ],
            },
        ),
        (
            "Processing",
            {
                "fields": [
                    "requested_by",
                    "executed_by",
                    "executed_at",
                ],
            },
        ),
        (
            "Blockchain",
            {
                "fields": [
                    "transaction",
                    "tx_link",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Errors",
            {
                "fields": [
                    "error_message",
                    "rejection_reason",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:uuid>/execute/",
                self.admin_site.admin_view(self.execute_view),
                name="tokens_mintrequest_execute",
            ),
            path(
                "<uuid:uuid>/retry/",
                self.admin_site.admin_view(self.retry_view),
                name="tokens_mintrequest_retry",
            ),
            path(
                "<uuid:uuid>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="tokens_mintrequest_reject",
            ),
        ]
        return custom_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def token_symbol(self, obj):
        token = obj.token
        return token.symbol if token else "-"

    token_symbol.short_description = "Token"

    def amount_display(self, obj):
        return obj.amount_display

    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"

    def status_badge(self, obj):
        colors = {
            MintRequestStatus.PENDING: "#17a2b8",
            MintRequestStatus.APPROVED: "#007bff",
            MintRequestStatus.EXECUTED: "#28a745",
            MintRequestStatus.FAILED: "#dc3545",
            MintRequestStatus.REJECTED: "#6c757d",
        }
        color = colors.get(obj.status, "#777777")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def tx_link(self, obj):
        if obj.transaction and obj.transaction.tx_hash:
            return format_html(
                '<code style="font-size: 12px;">{}</code>',
                obj.transaction.tx_hash,
            )
        return "-"

    tx_link.short_description = "Transaction Hash"

    def status_actions(self, obj):
        if obj.pk is None:
            return "-"

        buttons = []
        base_style = (
            "display: inline-block; padding: 6px 12px; margin: 2px; "
            "text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;"
        )

        if obj.status == MintRequestStatus.PENDING:
            execute_url = reverse("admin:tokens_mintrequest_execute", args=[obj.uuid])
            reject_url = reverse("admin:tokens_mintrequest_reject", args=[obj.uuid])
            buttons.append(
                f'<a href="{execute_url}" style="{base_style} background-color: #28a745; color: white;">'
                "Execute Mint</a>"
            )
            buttons.append(
                f'<a href="{reject_url}" style="{base_style} background-color: #dc3545; color: white;">' "Reject</a>"
            )

        elif obj.status == MintRequestStatus.FAILED:
            retry_url = reverse("admin:tokens_mintrequest_retry", args=[obj.uuid])
            reject_url = reverse("admin:tokens_mintrequest_reject", args=[obj.uuid])
            buttons.append(
                f'<a href="{retry_url}" style="{base_style} background-color: #fd7e14; color: white;">' "Retry</a>"
            )
            buttons.append(
                f'<a href="{reject_url}" style="{base_style} background-color: #dc3545; color: white;">' "Reject</a>"
            )

        elif obj.status == MintRequestStatus.EXECUTED:
            buttons.append(f'<span style="{base_style} background-color: #28a745; color: white;">' "Executed</span>")

        elif obj.status == MintRequestStatus.REJECTED:
            buttons.append(f'<span style="{base_style} background-color: #6c757d; color: white;">' "Rejected</span>")

        if not buttons:
            return "-"

        return mark_safe(" ".join(buttons))

    status_actions.short_description = "Quick Actions"

    def _get_service(self, mint_request):
        if mint_request.stablecoin:
            return StablecoinService(contract_address=mint_request.stablecoin.contract_address)
        elif mint_request.yield_token:
            return YieldTokenService(contract_address=mint_request.yield_token.contract_address)
        raise ValueError("Mint request has no associated token")

    def _get_related_model_label(self, mint_request):
        return "tokens.MintRequest"

    def execute_view(self, request, uuid):
        mint_request = get_object_or_404(MintRequest, uuid=uuid)

        if not mint_request.can_be_executed:
            messages.error(request, f"Cannot execute: request status is '{mint_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))

        if request.method == "POST":
            form = ExecuteMintForm(request.POST)
            if form.is_valid():
                additional_notes = form.cleaned_data.get("notes", "")
                if additional_notes:
                    mint_request.notes = f"{mint_request.notes}\n\nExecution notes: {additional_notes}"
                    mint_request.save(update_fields=["notes", "updated_at"])

                try:
                    service = self._get_service(mint_request)

                    tx_hash, tx_record = service.mint(
                        to_address=mint_request.recipient_address,
                        amount=mint_request.amount,
                        related_model=self._get_related_model_label(mint_request),
                        related_uuid=str(mint_request.uuid),
                    )

                    mint_request.mark_executed(user=request.user, transaction=tx_record)

                    token = mint_request.token
                    messages.success(
                        request,
                        f"Successfully minted {mint_request.amount_display} "
                        f"{token.symbol} to {mint_request.recipient_name} "
                        f"(tx: {tx_hash[:16]}...)",
                    )

                except Exception as e:
                    mint_request.mark_failed(str(e))
                    messages.error(request, f"Mint execution failed: {e}")
                    logger.exception(f"Mint execution failed for {mint_request.uuid}: {e}")

                return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))
        else:
            form = ExecuteMintForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Execute Mint: {mint_request.recipient_name}",
            "subtitle": None,
            "mint_request": mint_request,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/mintrequest/execute_form.html", context)

    def retry_view(self, request, uuid):
        mint_request = get_object_or_404(MintRequest, uuid=uuid)

        if not mint_request.can_retry:
            messages.error(request, f"Cannot retry: request status is '{mint_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))

        if request.method == "POST":
            form = RetryMintForm(request.POST)
            if form.is_valid():
                additional_notes = form.cleaned_data.get("notes", "")
                if additional_notes:
                    mint_request.notes = f"{mint_request.notes}\n\nRetry notes: {additional_notes}"
                    mint_request.save(update_fields=["notes", "updated_at"])

                try:
                    service = self._get_service(mint_request)

                    tx_hash, tx_record = service.mint(
                        to_address=mint_request.recipient_address,
                        amount=mint_request.amount,
                        related_model=self._get_related_model_label(mint_request),
                        related_uuid=str(mint_request.uuid),
                    )

                    mint_request.mark_executed(user=request.user, transaction=tx_record)

                    token = mint_request.token
                    messages.success(
                        request,
                        f"Successfully minted {mint_request.amount_display} " f"{token.symbol} (tx: {tx_hash[:16]}...)",
                    )

                except Exception as e:
                    mint_request.mark_failed(str(e))
                    messages.error(request, f"Retry failed: {e}")

                return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))
        else:
            form = RetryMintForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Retry Mint: {mint_request.recipient_name}",
            "subtitle": None,
            "mint_request": mint_request,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/mintrequest/retry_form.html", context)

    def reject_view(self, request, uuid):
        mint_request = get_object_or_404(MintRequest, uuid=uuid)

        if not mint_request.can_be_rejected:
            messages.error(request, f"Cannot reject: request status is '{mint_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))

        if request.method == "POST":
            form = RejectMintForm(request.POST)
            if form.is_valid():
                mint_request.mark_rejected(
                    user=request.user,
                    reason=form.cleaned_data["reason"],
                )
                messages.warning(
                    request,
                    f"Mint request rejected for {mint_request.recipient_name}",
                )
                return HttpResponseRedirect(reverse("admin:tokens_mintrequest_change", args=[mint_request.pk]))
        else:
            form = RejectMintForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Reject Mint: {mint_request.recipient_name}",
            "subtitle": None,
            "mint_request": mint_request,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/mintrequest/reject_form.html", context)
