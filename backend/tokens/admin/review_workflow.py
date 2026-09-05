from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from shared.utils.admin_display import action_buttons
from tokens.models import RequestStatus
from tokens.tasks import execute_review_request_task

from ._helpers import status_badge

STATUS_COLORS = {
    RequestStatus.DRAFT: "#6c757d",
    RequestStatus.SUBMITTED: "#17a2b8",
    RequestStatus.UNDER_REVIEW: "#007bff",
    RequestStatus.APPROVED: "#28a745",
    RequestStatus.REJECTED: "#dc3545",
    RequestStatus.EXECUTING: "#fd7e14",
    RequestStatus.EXECUTED: "#20c997",
    RequestStatus.FAILED: "#dc3545",
}
APPROVE = ("Approve", "approve", "#28a745")
REJECT = ("Reject", "reject", "#dc3545")
STATUS_ACTIONS = {
    RequestStatus.DRAFT: [("Awaiting Submission", None, "#e9ecef", "#6c757d")],
    RequestStatus.SUBMITTED: [("Start Review", "start_review", "#007bff"), APPROVE, REJECT],
    RequestStatus.UNDER_REVIEW: [APPROVE, REJECT],
    RequestStatus.APPROVED: [("Execute", "execute", "#fd7e14")],
    RequestStatus.FAILED: [("Retry Execute", "execute", "#fd7e14")],
    RequestStatus.EXECUTING: [("Executing...", None, "#fd7e14")],
    RequestStatus.EXECUTED: [("Executed", None, "#20c997")],
    RequestStatus.REJECTED: [("Request Rejected", None, "#e9ecef", "#6c757d")],
}


class ApproveForm(forms.Form):
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Review Notes (Optional)")


class RejectForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=True, label="Rejection Reason")


class ReviewWorkflowAdmin(admin.ModelAdmin):

    label = "Request"
    deletable_status = RequestStatus.DRAFT
    detail_fieldset = ("Details", {"fields": []})
    ordering = ["-created_at"]
    status_badge = status_badge(STATUS_COLORS)

    def describe(self, obj) -> str:
        return str(obj)

    def detail_rows(self, obj) -> list[tuple[str, str]]:
        return []

    def execution_steps(self, obj) -> list[str]:
        return []

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.opts.fields] + ["status_actions"]

    def get_fieldsets(self, request, obj=None):
        return [
            ("Request Information", {"fields": ["uuid", "token", "status", "status_actions"]}),
            self.detail_fieldset,
            ("Submission", {"fields": ["submitted_by", "submitted_at"]}),
            (
                "Review",
                {"fields": ["reviewed_by", "reviewed_at", "review_notes", "rejection_reason"], "classes": ["collapse"]},
            ),
            ("Execution", {"fields": ["executed_issuance", "executed_at"], "classes": ["collapse"]}),
            ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
        ]

    def get_urls(self):
        views = [
            ("start-review", "start_review", self.start_review_view),
            ("approve", "approve", self.approve_view),
            ("reject", "reject", self.reject_view),
            ("execute", "execute", self.execute_view),
        ]
        custom = [
            path(f"<uuid:uuid>/{slug}/", self.admin_site.admin_view(view), name=self._url_name(action))
            for slug, action, view in views
        ]
        return custom + super().get_urls()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status != self.deletable_status:
            return False
        return super().has_delete_permission(request, obj)

    def _url_name(self, action):
        return f"{self.opts.app_label}_{self.opts.model_name}_{action}"

    def _change_url(self, obj):
        return reverse(f"admin:{self._url_name('change')}", args=[obj.pk])

    @admin.display(description="Token", ordering="token__symbol")
    def token_symbol(self, obj):
        return obj.token.symbol

    @admin.display(description="Dilution")
    def dilution_display(self, obj):
        return f"{obj.dilution_percentage}%" if obj.dilution_percentage is not None else "-"

    @admin.display(description="Quick Actions")
    def status_actions(self, obj):
        if obj.pk is None:
            return "-"
        items = STATUS_ACTIONS.get(obj.status, [])
        return action_buttons(
            [
                (label, action and reverse(f"admin:{self._url_name(action)}", args=[obj.uuid]), *colors)
                for label, action, *colors in items
            ]
        )

    def _refuse(self, request, obj, verb):
        messages.error(request, f"Cannot {verb}: request status is '{obj.get_status_display()}'")
        return HttpResponseRedirect(self._change_url(obj))

    def _render(self, request, obj, action, form=None):
        context = {
            **self.admin_site.each_context(request),
            "title": f"{action.capitalize()} {self.label}: {obj.token.symbol}",
            "subtitle": None,
            "opts": self.opts,
            "action": action,
            "label": self.label,
            "review_request": obj,
            "form": form,
            "detail_rows": self.detail_rows(obj),
            "execution_steps": self.execution_steps(obj),
        }
        return render(request, "admin/tokens/review_request/action_form.html", context)

    def start_review_view(self, request, uuid):
        obj = get_object_or_404(self.model, uuid=uuid)
        if obj.status != RequestStatus.SUBMITTED:
            return self._refuse(request, obj, "start review")
        obj.start_review(request.user)
        messages.info(request, f"Review started for {obj.token.symbol} {self.label.lower()} request.")
        return HttpResponseRedirect(self._change_url(obj))

    def approve_view(self, request, uuid):
        obj = get_object_or_404(self.model, uuid=uuid)
        if not obj.can_be_approved:
            return self._refuse(request, obj, "approve")
        form = ApproveForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            obj.approve(reviewer=request.user, notes=form.cleaned_data["notes"])
            messages.success(
                request, f"{self.label} approved for {obj.token.symbol}: {self.describe(obj)}. Ready for execution."
            )
            return HttpResponseRedirect(self._change_url(obj))
        return self._render(request, obj, "approve", form)

    def reject_view(self, request, uuid):
        obj = get_object_or_404(self.model, uuid=uuid)
        if not obj.can_be_approved:
            return self._refuse(request, obj, "reject")
        form = RejectForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            obj.reject(reviewer=request.user, reason=form.cleaned_data["reason"])
            messages.warning(request, f"{self.label} rejected for {obj.token.symbol}")
            return HttpResponseRedirect(self._change_url(obj))
        return self._render(request, obj, "reject", form)

    def execute_view(self, request, uuid):
        obj = get_object_or_404(self.model, uuid=uuid)
        if not obj.can_be_executed:
            return self._refuse(request, obj, "execute")
        if request.method == "POST":
            execute_review_request_task.defer(
                model_label=self.opts.label, request_uuid=str(obj.uuid), executed_by=request.user.pk
            )
            messages.info(
                request,
                f"{self.label} execution started for {obj.token.symbol}. The task is running in the background.",
            )
            return HttpResponseRedirect(self._change_url(obj))
        return self._render(request, obj, "execute")
