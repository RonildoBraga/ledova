from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tokens.models import ShareIssuanceRequest
from tokens.models.choices import IssuanceRequestStatus
from tokens.tasks import execute_share_issuance_request_task


class ApproveIssuanceForm(forms.Form):
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Review Notes (Optional)",
    )


class RejectIssuanceForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        label="Rejection Reason",
    )


@admin.register(ShareIssuanceRequest)
class ShareIssuanceRequestAdmin(admin.ModelAdmin):
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
    readonly_fields = [
        "uuid",
        "token",
        "recipient_address",
        "recipient_name",
        "amount",
        "issuance_type",
        "reason",
        "status",
        "dilution_percentage",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "review_notes",
        "rejection_reason",
        "executed_issuance",
        "executed_at",
        "created_at",
        "updated_at",
        "status_actions",
    ]
    ordering = ["-created_at"]

    fieldsets = [
        (
            "Request Information",
            {
                "fields": [
                    "uuid",
                    "token",
                    "status",
                    "status_actions",
                ],
            },
        ),
        (
            "Issuance Details",
            {
                "fields": [
                    "recipient_address",
                    "recipient_name",
                    "amount",
                    "issuance_type",
                    "reason",
                    "dilution_percentage",
                ],
            },
        ),
        (
            "Submission",
            {
                "fields": [
                    "submitted_by",
                    "submitted_at",
                ],
            },
        ),
        (
            "Review",
            {
                "fields": [
                    "reviewed_by",
                    "reviewed_at",
                    "review_notes",
                    "rejection_reason",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Execution",
            {
                "fields": [
                    "executed_issuance",
                    "executed_at",
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
                "<uuid:uuid>/start-review/",
                self.admin_site.admin_view(self.start_review_view),
                name="tokens_shareissuancerequest_start_review",
            ),
            path(
                "<uuid:uuid>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="tokens_shareissuancerequest_approve",
            ),
            path(
                "<uuid:uuid>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="tokens_shareissuancerequest_reject",
            ),
            path(
                "<uuid:uuid>/execute/",
                self.admin_site.admin_view(self.execute_view),
                name="tokens_shareissuancerequest_execute",
            ),
        ]
        return custom_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status != IssuanceRequestStatus.PENDING_APPROVAL:
            return False
        return super().has_delete_permission(request, obj)

    def token_symbol(self, obj):
        return obj.token.symbol

    token_symbol.short_description = "Token"
    token_symbol.admin_order_field = "token__symbol"

    def recipient_display(self, obj):
        if obj.recipient_name:
            return f"{obj.recipient_name} ({obj.recipient_address[:10]}...)"
        return f"{obj.recipient_address[:10]}..."

    recipient_display.short_description = "Recipient"

    def dilution_display(self, obj):
        if obj.dilution_percentage is not None:
            return f"{obj.dilution_percentage}%"
        return "-"

    dilution_display.short_description = "Dilution"

    def status_badge(self, obj):
        colors = {
            IssuanceRequestStatus.PENDING_APPROVAL: "#17a2b8",
            IssuanceRequestStatus.UNDER_REVIEW: "#007bff",
            IssuanceRequestStatus.APPROVED: "#28a745",
            IssuanceRequestStatus.REJECTED: "#dc3545",
            IssuanceRequestStatus.EXECUTING: "#fd7e14",
            IssuanceRequestStatus.EXECUTED: "#20c997",
            IssuanceRequestStatus.FAILED: "#dc3545",
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

    def status_actions(self, obj):
        if obj.pk is None:
            return "-"

        buttons = []
        base_style = (
            "display: inline-block; padding: 6px 12px; margin: 2px; "
            "text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;"
        )

        if obj.status == IssuanceRequestStatus.PENDING_APPROVAL:
            start_review_url = reverse("admin:tokens_shareissuancerequest_start_review", args=[obj.uuid])
            buttons.append(
                f'<a href="{start_review_url}" style="{base_style} background-color: #007bff; color: white;">'
                "Start Review</a>"
            )

        if obj.status in [IssuanceRequestStatus.PENDING_APPROVAL, IssuanceRequestStatus.UNDER_REVIEW]:
            approve_url = reverse("admin:tokens_shareissuancerequest_approve", args=[obj.uuid])
            reject_url = reverse("admin:tokens_shareissuancerequest_reject", args=[obj.uuid])
            buttons.append(
                f'<a href="{approve_url}" style="{base_style} background-color: #28a745; color: white;">' "Approve</a>"
            )
            buttons.append(
                f'<a href="{reject_url}" style="{base_style} background-color: #dc3545; color: white;">' "Reject</a>"
            )

        elif obj.status == IssuanceRequestStatus.APPROVED:
            execute_url = reverse("admin:tokens_shareissuancerequest_execute", args=[obj.uuid])
            buttons.append(
                f'<a href="{execute_url}" style="{base_style} background-color: #fd7e14; color: white;">' "Execute</a>"
            )

        elif obj.status == IssuanceRequestStatus.FAILED:
            execute_url = reverse("admin:tokens_shareissuancerequest_execute", args=[obj.uuid])
            buttons.append(
                f'<a href="{execute_url}" style="{base_style} background-color: #fd7e14; color: white;">'
                "Retry Execute</a>"
            )

        elif obj.status == IssuanceRequestStatus.REJECTED:
            buttons.append(
                f'<span style="{base_style} background-color: #e9ecef; color: #6c757d;">' "Request Rejected</span>"
            )

        elif obj.status == IssuanceRequestStatus.EXECUTED:
            buttons.append(f'<span style="{base_style} background-color: #20c997; color: white;">' "Executed</span>")

        elif obj.status == IssuanceRequestStatus.EXECUTING:
            buttons.append(
                f'<span style="{base_style} background-color: #fd7e14; color: white;">' "Executing...</span>"
            )

        if not buttons:
            return "-"

        return mark_safe(" ".join(buttons))

    status_actions.short_description = "Quick Actions"

    def start_review_view(self, request, uuid):
        issuance_request = get_object_or_404(ShareIssuanceRequest, uuid=uuid)

        if issuance_request.status != IssuanceRequestStatus.PENDING_APPROVAL:
            messages.error(request, f"Cannot start review: request status is '{issuance_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk]))

        issuance_request.start_review(request.user)
        messages.info(request, f"Review started for {issuance_request.token.symbol} issuance request.")
        return HttpResponseRedirect(reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk]))

    def approve_view(self, request, uuid):
        issuance_request = get_object_or_404(ShareIssuanceRequest, uuid=uuid)

        if not issuance_request.can_be_approved:
            messages.error(request, f"Cannot approve: request status is '{issuance_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk]))

        if request.method == "POST":
            form = ApproveIssuanceForm(request.POST)
            if form.is_valid():
                issuance_request.approve(
                    reviewer=request.user,
                    notes=form.cleaned_data.get("notes", ""),
                )
                messages.success(
                    request,
                    f"Issuance request approved for {issuance_request.token.symbol}: "
                    f"{issuance_request.amount} shares to {issuance_request.recipient_address[:10]}... "
                    f"Ready for execution.",
                )
                return HttpResponseRedirect(
                    reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk])
                )
        else:
            form = ApproveIssuanceForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Approve Share Issuance: {issuance_request.token.symbol}",
            "subtitle": None,
            "issuance_request": issuance_request,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/shareissuancerequest/approve_form.html", context)

    def reject_view(self, request, uuid):
        issuance_request = get_object_or_404(ShareIssuanceRequest, uuid=uuid)

        if not issuance_request.can_be_approved:
            messages.error(request, f"Cannot reject: request status is '{issuance_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk]))

        if request.method == "POST":
            form = RejectIssuanceForm(request.POST)
            if form.is_valid():
                issuance_request.reject(
                    reviewer=request.user,
                    reason=form.cleaned_data["reason"],
                )
                messages.warning(request, f"Issuance request rejected for {issuance_request.token.symbol}")
                return HttpResponseRedirect(
                    reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk])
                )
        else:
            form = RejectIssuanceForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Reject Share Issuance: {issuance_request.token.symbol}",
            "subtitle": None,
            "issuance_request": issuance_request,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/shareissuancerequest/reject_form.html", context)

    def execute_view(self, request, uuid):
        issuance_request = get_object_or_404(ShareIssuanceRequest, uuid=uuid)

        if not issuance_request.can_be_executed and not issuance_request.can_retry_execution:
            messages.error(request, f"Cannot execute: request status is '{issuance_request.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk]))

        if request.method == "POST":
            execute_share_issuance_request_task.defer(request_uuid=str(issuance_request.uuid))
            messages.info(
                request,
                f"Issuance execution started for {issuance_request.token.symbol}. "
                f"The task is running in the background.",
            )
            return HttpResponseRedirect(reverse("admin:tokens_shareissuancerequest_change", args=[issuance_request.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Execute Share Issuance: {issuance_request.token.symbol}",
            "subtitle": None,
            "issuance_request": issuance_request,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/shareissuancerequest/execute_form.html", context)
