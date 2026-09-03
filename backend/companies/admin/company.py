from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, re_path, reverse
from django.utils.html import format_html

from companies.exceptions import InvalidStatusTransitionException
from companies.models import (
    ApplicationReview,
    Company,
    CompanyDocument,
    CompanyStatus,
)
from tokens.admin._helpers import action_buttons, status_badge

User = get_user_model()

STATUS_COLORS = {
    CompanyStatus.DRAFT: "#6c757d",
    CompanyStatus.SUBMITTED: "#17a2b8",
    CompanyStatus.REVIEW: "#007bff",
    CompanyStatus.INFO_REQUIRED: "#fd7e14",
    CompanyStatus.APPROVED: "#20c997",
    CompanyStatus.ACTIVE: "#28a745",
    CompanyStatus.WARNING: ("#ffc107", "black"),
    CompanyStatus.SUSPENDED: "#dc3545",
    CompanyStatus.DELISTED: "#343a40",
    CompanyStatus.REJECTED: "#6c757d",
    CompanyStatus.WITHDRAWN: "#adb5bd",
}

# URL slug -> the Company transition it drives. Entries with a `label` ask for a reason on a form page first;
# `actor` names the kwarg that receives the acting staff user; `level` is the message level on success.
TRANSITIONS = {
    "start-review": dict(method="start_review", done="Review started for '{name}'."),
    "approve": dict(method="approve", actor="approved_by", done="Company '{name}' has been approved."),
    "activate": dict(method="activate", done="Company '{name}' is now active on the platform."),
    "resolve-warning": dict(method="resolve_warning", done="Warning resolved for '{name}'. Company is now active."),
    "reinstate": dict(method="reinstate", done="Company '{name}' has been reinstated and is now active."),
    "request-info": dict(
        method="request_info",
        title="Request Information",
        alert="warning",
        heading="Information Request",
        intro=(
            "You are requesting additional information from {name} (ACN: {acn}). The company will be notified "
            'and the application status will change to "Additional Information Required".'
        ),
        legend="Information Request Details",
        label="Information Requested",
        help="Describe what additional information is needed from the company.",
        button=("Request Information", "btn-warning"),
        done="Additional information requested from '{name}'.",
    ),
    "reject": dict(
        method="reject",
        actor="rejected_by",
        title="Reject Application",
        alert="warning",
        heading="Warning",
        intro=(
            "You are about to reject the company registration for {name} (ACN: {acn}). "
            "This action will notify the company that their registration has been rejected."
        ),
        legend="Rejection Details",
        label="Rejection Reason",
        help="Provide a clear reason for rejecting this company application.",
        button=("Reject Company", "btn-danger"),
        done="Company '{name}' application has been rejected.",
    ),
    "issue-warning": dict(
        method="issue_warning",
        title="Issue Warning",
        alert="warning",
        heading="Compliance Warning",
        intro=(
            "You are issuing a compliance warning to {name} (ACN: {acn}). The company will be notified "
            'and their status will change to "Compliance Warning".'
        ),
        legend="Warning Details",
        label="Warning Reason",
        help="Describe the compliance issue.",
        button=("Issue Warning", "btn-warning"),
        done="Warning issued to '{name}'.",
        level=messages.WARNING,
    ),
    "suspend": dict(
        method="suspend",
        title="Suspend Company",
        alert="warning",
        heading="Warning",
        intro=(
            "You are about to suspend the company {name}. "
            "A suspended company cannot perform any operations until reactivated."
        ),
        legend="Suspension Details",
        label="Suspension Reason",
        help="Provide a reason for suspending this company.",
        button=("Suspend Company", "btn-warning"),
        done="Company '{name}' has been suspended.",
        level=messages.WARNING,
    ),
    "delist": dict(
        method="delist",
        title="Delist Company",
        alert="danger",
        heading="PERMANENT ACTION",
        intro=(
            "You are about to permanently delist {name} (ACN: {acn}). This action cannot be undone. "
            "The company will be removed from the platform and will no longer be able to operate."
        ),
        legend="Delisting Details",
        label="Delisting Reason",
        help="Provide a reason for permanently delisting this company.",
        button=("Permanently Delist Company", "btn-dark"),
        done="Company '{name}' has been permanently delisted.",
        level=messages.ERROR,
    ),
}

ASSIGN_REVIEWERS = ("👥 Assign Reviewers", "assign-reviewers", "#6f42c1")
REJECT = ("✗ Reject", "reject", "#dc3545")
SUSPEND = ("⏸ Suspend", "suspend", "#dc3545")
DELIST = ("✗ Delist", "delist", "#343a40")
STATUS_BUTTONS = {
    CompanyStatus.SUBMITTED: [ASSIGN_REVIEWERS, ("▶ Start Review", "start-review", "#007bff"), REJECT],
    CompanyStatus.REVIEW: [
        ASSIGN_REVIEWERS,
        ("? Request Info", "request-info", "#fd7e14"),
        ("✓ Approve", "approve", "#20c997"),
        REJECT,
    ],
    CompanyStatus.INFO_REQUIRED: [("⏳ Awaiting Response", None, "#fd7e14")],
    CompanyStatus.APPROVED: [("✓ Activate Company", "activate", "#28a745")],
    CompanyStatus.ACTIVE: [("⚠ Issue Warning", "issue-warning", "#ffc107", "black"), SUSPEND, DELIST],
    CompanyStatus.WARNING: [("✓ Resolve Warning", "resolve-warning", "#28a745"), SUSPEND, DELIST],
    CompanyStatus.SUSPENDED: [("↻ Reinstate", "reinstate", "#28a745"), DELIST],
    CompanyStatus.DRAFT: [("Draft - Not Submitted", None, "#e9ecef", "#6c757d")],
    CompanyStatus.REJECTED: [("Application Rejected", None, "#e9ecef", "#6c757d")],
    CompanyStatus.WITHDRAWN: [("Application Withdrawn", None, "#e9ecef", "#6c757d")],
    CompanyStatus.DELISTED: [("Permanently Delisted", None, "#e9ecef", "#6c757d")],
}


class CompanyDocumentInline(admin.TabularInline):
    model = CompanyDocument
    extra = 0
    fields = ["document_type", "name", "file_link", "is_verified", "created_at"]
    readonly_fields = ["file_link", "is_verified", "created_at"]

    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">View File</a>', obj.file.url)
        elif obj.external_url:
            return format_html('<a href="{}" target="_blank">External Link</a>', obj.external_url)
        return "-"

    file_link.short_description = "File"


class ApplicationReviewInline(admin.TabularInline):
    model = ApplicationReview
    extra = 0
    fields = ["review_order", "reviewer", "decision", "decision_at", "decision_reason"]
    readonly_fields = ["decision_at"]
    can_delete = False


class AssignReviewersForm(forms.Form):
    reviewer_1 = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True, is_active=True),
        label="Primary Reviewer",
        help_text="First reviewer to evaluate the application.",
    )
    reviewer_2 = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True, is_active=True),
        label="Secondary Reviewer",
        help_text="Second reviewer to evaluate the application.",
    )

    def clean(self):
        cleaned_data = super().clean()
        reviewer_1 = cleaned_data.get("reviewer_1")
        reviewer_2 = cleaned_data.get("reviewer_2")
        if reviewer_1 and reviewer_2 and reviewer_1 == reviewer_2:
            raise forms.ValidationError("Reviewers must be different people.")
        return cleaned_data


class ReasonForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 4, "cols": 60}))

    def __init__(self, *args, label, help_text, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].label = label
        self.fields["reason"].help_text = help_text


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "acn",
        "company_type",
        "status_badge",
        "owner_email",
        "city",
        "state",
        "created_at",
    ]
    list_filter = ["status", "company_type", "state", "created_at"]
    search_fields = ["name", "trading_name", "acn", "abn", "owner__email"]
    readonly_fields = [
        "uuid",
        "api_key",
        "api_key_created_at",
        "submitted_at",
        "review_started_at",
        "review_completed_at",
        "approved_at",
        "activated_at",
        "rejection_at",
        "info_requested_at",
        "warning_issued_at",
        "suspended_at",
        "delisted_at",
        "withdrawn_at",
        "created_at",
        "updated_at",
        "status_actions",
    ]
    ordering = ["-created_at"]

    fieldsets = [
        (
            "Company Information",
            {
                "fields": [
                    "uuid",
                    "owner",
                    "name",
                    "trading_name",
                    "company_type",
                    "acn",
                    "abn",
                ]
            },
        ),
        (
            "Status & Actions",
            {
                "fields": [
                    "status",
                    "status_actions",
                ]
            },
        ),
        (
            "Application Tracking",
            {
                "fields": [
                    "submitted_at",
                    "review_started_at",
                    "info_requested_at",
                    "info_request_reason",
                    "review_completed_at",
                    "approved_at",
                    "activated_at",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Rejection / Compliance",
            {
                "fields": [
                    "rejection_reason",
                    "rejection_at",
                    "warning_reason",
                    "warning_issued_at",
                    "suspension_reason",
                    "suspended_at",
                    "delisting_reason",
                    "delisted_at",
                    "withdrawal_reason",
                    "withdrawn_at",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Contact Information",
            {
                "fields": [
                    "phone",
                ]
            },
        ),
        (
            "Address",
            {
                "fields": [
                    "address_line_1",
                    "address_line_2",
                    "city",
                    "state",
                    "postcode",
                    "country",
                ]
            },
        ),
        (
            "API Access",
            {
                "fields": [
                    "api_key",
                    "api_key_created_at",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Additional Information",
            {
                "fields": [
                    "description",
                    "industry",
                    "founded_year",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    inlines = [ApplicationReviewInline, CompanyDocumentInline]

    actions = ["start_review_action", "approve_action", "activate_action"]

    status_badge = status_badge(STATUS_COLORS)

    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:uuid>/assign-reviewers/",
                self.admin_site.admin_view(self.assign_reviewers_view),
                name="companies_company_assign_reviewers",
            ),
            re_path(
                rf"^(?P<uuid>[0-9a-f-]+)/(?P<action>{'|'.join(TRANSITIONS)})/$",
                self.admin_site.admin_view(self.transition_view),
                name="companies_company_transition",
            ),
        ]
        return custom_urls + super().get_urls()

    def owner_email(self, obj):
        return obj.email

    owner_email.short_description = "Email"
    owner_email.admin_order_field = "owner__email"

    def _action_url(self, obj, slug):
        if slug is None:
            return None
        if slug == "assign-reviewers":
            return reverse("admin:companies_company_assign_reviewers", args=[obj.uuid])
        return reverse("admin:companies_company_transition", args=[obj.uuid, slug])

    @admin.display(description="Quick Actions")
    def status_actions(self, obj):
        if obj.pk is None:
            return "-"
        return action_buttons(
            [
                (label, self._action_url(obj, slug), *colors)
                for label, slug, *colors in STATUS_BUTTONS.get(obj.status, [])
            ]
        )

    def transition_view(self, request, uuid, action):
        company = get_object_or_404(Company, uuid=uuid)
        spec = TRANSITIONS[action]
        change_url = reverse("admin:companies_company_change", args=[company.pk])
        kwargs = {spec["actor"]: request.user} if "actor" in spec else {}

        if "label" in spec:
            form = ReasonForm(request.POST or None, label=spec["label"], help_text=spec["help"])
            if request.method != "POST" or not form.is_valid():
                context = {
                    **self.admin_site.each_context(request),
                    "title": f"{spec['title']}: {company.name}",
                    "subtitle": None,
                    "opts": self.opts,
                    "company": company,
                    "form": form,
                    "transition": spec,
                    "intro": spec["intro"].format(name=company.name, acn=company.acn),
                }
                return render(request, "admin/companies/company/transition_form.html", context)
            kwargs["reason"] = form.cleaned_data["reason"]

        try:
            getattr(company, spec["method"])(**kwargs)
        except InvalidStatusTransitionException as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.add_message(request, spec.get("level", messages.SUCCESS), spec["done"].format(name=company.name))
        return HttpResponseRedirect(change_url)

    def assign_reviewers_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status not in [CompanyStatus.SUBMITTED, CompanyStatus.REVIEW]:
            messages.error(
                request,
                f"Cannot assign reviewers: status is '{company.get_status_display()}'",
            )
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        if request.method == "POST":
            form = AssignReviewersForm(request.POST)
            if form.is_valid():
                from companies.services import ReviewService

                reviewers = [
                    form.cleaned_data["reviewer_1"],
                    form.cleaned_data["reviewer_2"],
                ]
                ReviewService.assign_reviewers(
                    company=company,
                    reviewers=reviewers,
                    assigned_by=request.user,
                )

                if company.status == CompanyStatus.SUBMITTED:
                    company.start_review()

                messages.success(
                    request,
                    f"Reviewers assigned to '{company.name}': " f"{reviewers[0].email} and {reviewers[1].email}",
                )
                return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))
        else:
            form = AssignReviewersForm()

        existing_reviews = ApplicationReview.objects.filter(company=company)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Assign Reviewers: {company.name}",
            "subtitle": None,
            "company": company,
            "form": form,
            "existing_reviews": existing_reviews,
            "opts": self.model._meta,
        }
        return render(request, "admin/companies/company/assign_reviewers_form.html", context)

    @admin.action(description="Start review for selected submitted applications")
    def start_review_action(self, request, queryset):
        count = 0
        for company in queryset.filter(status=CompanyStatus.SUBMITTED):
            company.start_review()
            count += 1
        self.message_user(request, f"Review started for {count} applications.")

    @admin.action(description="Approve selected applications under review")
    def approve_action(self, request, queryset):
        count = 0
        for company in queryset.filter(status=CompanyStatus.REVIEW):
            company.approve(approved_by=request.user)
            count += 1
        self.message_user(request, f"{count} applications approved.")

    @admin.action(description="Activate selected approved companies")
    def activate_action(self, request, queryset):
        count = 0
        for company in queryset.filter(status=CompanyStatus.APPROVED):
            company.activate()
            count += 1
        self.message_user(request, f"{count} companies activated.")
