from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from tokens.models import CapitalIncreaseRequest, CapitalIncreaseStatus
from tokens.tasks import execute_capital_increase_task


class ApproveRequestForm(forms.Form):
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Review Notes (Optional)",
    )


class RejectRequestForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=True,
        label="Rejection Reason",
    )


@admin.register(CapitalIncreaseRequest)
class CapitalIncreaseAdmin(admin.ModelAdmin):
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
    search_fields = [
        "token__symbol",
        "token__name",
        "purpose",
        "submitted_by__email",
    ]
    readonly_fields = [
        "uuid",
        "token",
        "additional_shares",
        "new_authorized_total",
        "purpose",
        "board_resolution_reference",
        "shareholder_approval_reference",
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
            "Capital Increase Details",
            {
                "fields": [
                    "additional_shares",
                    "new_authorized_total",
                    "purpose",
                    "board_resolution_reference",
                    "shareholder_approval_reference",
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
                name="tokens_capitalincreaserequest_start_review",
            ),
            path(
                "<uuid:uuid>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="tokens_capitalincreaserequest_approve",
            ),
            path(
                "<uuid:uuid>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="tokens_capitalincreaserequest_reject",
            ),
            path(
                "<uuid:uuid>/execute/",
                self.admin_site.admin_view(self.execute_view),
                name="tokens_capitalincreaserequest_execute",
            ),
        ]
        return custom_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status != CapitalIncreaseStatus.DRAFT:
            return False
        return super().has_delete_permission(request, obj)

    def token_symbol(self, obj):
        return obj.token.symbol

    token_symbol.short_description = "Token"
    token_symbol.admin_order_field = "token__symbol"

    def dilution_display(self, obj):
        if obj.dilution_percentage is not None:
            return f"{obj.dilution_percentage}%"
        return "-"

    dilution_display.short_description = "Dilution"

    def status_badge(self, obj):
        colors = {
            CapitalIncreaseStatus.DRAFT: "#6c757d",
            CapitalIncreaseStatus.SUBMITTED: "#17a2b8",
            CapitalIncreaseStatus.UNDER_REVIEW: "#007bff",
            CapitalIncreaseStatus.APPROVED: "#28a745",
            CapitalIncreaseStatus.REJECTED: "#dc3545",
            CapitalIncreaseStatus.EXECUTING: "#fd7e14",
            CapitalIncreaseStatus.EXECUTED: "#20c997",
            CapitalIncreaseStatus.FAILED: "#dc3545",
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

        if obj.status == CapitalIncreaseStatus.SUBMITTED:
            start_review_url = reverse("admin:tokens_capitalincreaserequest_start_review", args=[obj.uuid])
            buttons.append(
                f'<a href="{start_review_url}" style="{base_style} background-color: #007bff; color: white;">'
                "📋 Start Review</a>"
            )

        if obj.status in [CapitalIncreaseStatus.SUBMITTED, CapitalIncreaseStatus.UNDER_REVIEW]:
            approve_url = reverse("admin:tokens_capitalincreaserequest_approve", args=[obj.uuid])
            reject_url = reverse("admin:tokens_capitalincreaserequest_reject", args=[obj.uuid])
            buttons.append(
                f'<a href="{approve_url}" style="{base_style} background-color: #28a745; color: white;">'
                "✓ Approve</a>"
            )
            buttons.append(
                f'<a href="{reject_url}" style="{base_style} background-color: #dc3545; color: white;">' "✗ Reject</a>"
            )

        elif obj.status == CapitalIncreaseStatus.APPROVED:
            execute_url = reverse("admin:tokens_capitalincreaserequest_execute", args=[obj.uuid])
            buttons.append(
                f'<a href="{execute_url}" style="{base_style} background-color: #fd7e14; color: white;">'
                "⚡ Execute</a>"
            )

        elif obj.status == CapitalIncreaseStatus.FAILED:
            execute_url = reverse("admin:tokens_capitalincreaserequest_execute", args=[obj.uuid])
            buttons.append(
                f'<a href="{execute_url}" style="{base_style} background-color: #fd7e14; color: white;">'
                "🔄 Retry Execute</a>"
            )

        elif obj.status == CapitalIncreaseStatus.REJECTED:
            buttons.append(
                f'<span style="{base_style} background-color: #e9ecef; color: #6c757d;">' "Request Rejected</span>"
            )

        elif obj.status == CapitalIncreaseStatus.EXECUTED:
            buttons.append(f'<span style="{base_style} background-color: #20c997; color: white;">' "✓ Executed</span>")

        elif obj.status == CapitalIncreaseStatus.EXECUTING:
            buttons.append(
                f'<span style="{base_style} background-color: #fd7e14; color: white;">' "⏳ Executing...</span>"
            )

        elif obj.status == CapitalIncreaseStatus.DRAFT:
            buttons.append(
                f'<span style="{base_style} background-color: #e9ecef; color: #6c757d;">' "Awaiting Submission</span>"
            )

        if not buttons:
            return "-"

        return mark_safe(" ".join(buttons))

    status_actions.short_description = "Quick Actions"

    def start_review_view(self, request, uuid):
        capital_increase = get_object_or_404(CapitalIncreaseRequest, uuid=uuid)

        if capital_increase.status != CapitalIncreaseStatus.SUBMITTED:
            messages.error(request, f"Cannot start review: request status is '{capital_increase.get_status_display()}'")
            return HttpResponseRedirect(
                reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
            )

        capital_increase.start_review(request.user)
        messages.info(request, f"Review started for {capital_increase.token.symbol} capital increase request.")
        return HttpResponseRedirect(reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk]))

    def approve_view(self, request, uuid):
        capital_increase = get_object_or_404(CapitalIncreaseRequest, uuid=uuid)

        if not capital_increase.can_be_approved:
            messages.error(request, f"Cannot approve: request status is '{capital_increase.get_status_display()}'")
            return HttpResponseRedirect(
                reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
            )

        if request.method == "POST":
            form = ApproveRequestForm(request.POST)
            if form.is_valid():
                capital_increase.approve(
                    reviewer=request.user,
                    notes=form.cleaned_data.get("notes", ""),
                )
                messages.success(
                    request,
                    f"Capital increase approved for {capital_increase.token.symbol}: "
                    f"+{capital_increase.additional_shares} shares. Ready for execution.",
                )
                return HttpResponseRedirect(
                    reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
                )
        else:
            form = ApproveRequestForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Approve Capital Increase: {capital_increase.token.symbol}",
            "subtitle": None,
            "capital_increase": capital_increase,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/capitalincreaserequest/approve_form.html", context)

    def reject_view(self, request, uuid):
        capital_increase = get_object_or_404(CapitalIncreaseRequest, uuid=uuid)

        if not capital_increase.can_be_approved:
            messages.error(request, f"Cannot reject: request status is '{capital_increase.get_status_display()}'")
            return HttpResponseRedirect(
                reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
            )

        if request.method == "POST":
            form = RejectRequestForm(request.POST)
            if form.is_valid():
                capital_increase.reject(
                    reviewer=request.user,
                    reason=form.cleaned_data["reason"],
                )
                messages.warning(request, f"Capital increase rejected for {capital_increase.token.symbol}")
                return HttpResponseRedirect(
                    reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
                )
        else:
            form = RejectRequestForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Reject Capital Increase: {capital_increase.token.symbol}",
            "subtitle": None,
            "capital_increase": capital_increase,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/capitalincreaserequest/reject_form.html", context)

    def execute_view(self, request, uuid):
        capital_increase = get_object_or_404(CapitalIncreaseRequest, uuid=uuid)

        if not capital_increase.can_be_executed and not capital_increase.can_retry_execution:
            messages.error(request, f"Cannot execute: request status is '{capital_increase.get_status_display()}'")
            return HttpResponseRedirect(
                reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
            )

        if request.method == "POST":
            execute_capital_increase_task.defer(request_uuid=str(capital_increase.uuid))
            messages.info(
                request,
                f"Capital increase execution started for {capital_increase.token.symbol}. "
                f"The task is running in the background.",
            )
            return HttpResponseRedirect(
                reverse("admin:tokens_capitalincreaserequest_change", args=[capital_increase.pk])
            )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Execute Capital Increase: {capital_increase.token.symbol}",
            "subtitle": None,
            "capital_increase": capital_increase,
            "opts": self.model._meta,
        }
        return render(request, "admin/tokens/capitalincreaserequest/execute_form.html", context)
