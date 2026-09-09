from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from companies.models import (
    Company,
    CompanyDocument,
    CompanyRegistryCheck,
    CompanyStatus,
)
from companies.services import transition_company
from companies.services.editing import EDITABLE_FIELDS, update_company
from shared.utils.admin_actions import admin_action_re_path
from shared.utils.admin_display import action_buttons
from tokens.admin._helpers import status_badge
from wallets.models import Wallet

IMMUTABLE_AFTER_DRAFT = ("company_type", "acn", "abn")

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


TRANSITIONS = {
    "start-review": dict(method="start_review", done="Review started for '{name}'."),
    "approve": dict(method="approve", actor="approved_by", done="Company '{name}' has been approved."),
    "activate": dict(method="activate", done="Company '{name}' is now active on the platform."),
    "resolve-warning": dict(method="resolve_warning", done="Warning resolved for '{name}'. Company is now active."),
    "reinstate": dict(method="reinstate", done="Company '{name}' has been reinstated and is now active."),
    "retry-registry": dict(method="retry_registry", done="Registry check recorded for '{name}'."),
    "request-info": dict(
        method="request_info",
        title="Request Information",
        alert="warning",
        heading="Information Request",
        intro=(
            "You are requesting additional information from {name} (ACN: {acn}). The owner receives an in-app "
            'notification carrying this request and the application status changes to "Additional Information '
            'Required"; their answer appears under Application Tracking when they resubmit.'
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
            "The owner receives an in-app notification carrying this reason."
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
            "You are issuing a compliance warning to {name} (ACN: {acn}). Their status will change to "
            '"Compliance Warning"; the reason is recorded on the company and no notification is sent.'
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

for action, spec in TRANSITIONS.items():
    title = action.replace("-", " ").title()
    spec.setdefault("title", title)
    spec.setdefault("alert", "info")
    spec.setdefault("heading", title)
    spec.setdefault("intro", "Confirm this action for {name} (ACN: {acn}).")
    spec.setdefault("legend", "Review confirmation")
    spec.setdefault("button", (title, "btn-primary"))

REJECT = ("✗ Reject", "reject", "#dc3545")
SUSPEND = ("⏸ Suspend", "suspend", "#dc3545")
DELIST = ("✗ Delist", "delist", "#343a40")
STATUS_BUTTONS = {
    CompanyStatus.SUBMITTED: [("▶ Start Review", "start-review", "#007bff"), REJECT],
    CompanyStatus.REVIEW: [("? Request Info", "request-info", "#fd7e14"), ("✓ Approve", "approve", "#20c997"), REJECT],
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

for review_status in (
    CompanyStatus.REVIEW,
    CompanyStatus.APPROVED,
    CompanyStatus.ACTIVE,
    CompanyStatus.WARNING,
    CompanyStatus.SUSPENDED,
):
    STATUS_BUTTONS[review_status].append(("Retry Registry Check", "retry-registry", "#007bff"))


class CompanyRegistryCheckInline(admin.TabularInline):
    model = CompanyRegistryCheck
    fk_name = "company"
    extra = 0
    fields = (
        "started_at",
        "completed_at",
        "initiated_by",
        "purpose",
        "requested_name",
        "requested_acn",
        "requested_abn",
        "status",
        "reason",
        "entity_name",
        "entity_status",
        "registry_acn",
        "registry_abn",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("companies.view_company")


class CompanyDocumentInline(admin.TabularInline):
    model = CompanyDocument
    extra = 0
    fields = ["document_type", "name", "file_link", "is_verified", "created_at"]
    readonly_fields = ["file_link", "is_verified", "created_at"]

    def file_link(self, obj):
        if obj.pk is not None and obj.file:
            url = reverse("admin:companies_companydocument_file", args=[obj.uuid])
            return format_html('<a href="{}" target="_blank">View File</a>', url)
        elif obj.external_url:
            return format_html('<a href="{}" target="_blank">External Link</a>', obj.external_url)
        return "-"

    file_link.short_description = "File"


class TransitionForm(forms.Form):
    confirm = forms.BooleanField(label="Confirm this company action")
    declarant_name = forms.CharField(max_length=255, label="Named officeholder making the declaration")
    board_resolution_reference = forms.CharField(max_length=255, label="Board-resolution reference")
    attest_officeholder = forms.BooleanField(
        label=(
            "I attest that the named declarant is an officeholder and has a board resolution "
            "authorising this application."
        )
    )
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 4, "cols": 60}))

    def __init__(self, *args, spec, attestation_required, **kwargs):
        super().__init__(*args, **kwargs)
        if "label" in spec:
            self.fields["reason"].label = spec["label"]
            self.fields["reason"].help_text = spec["help"]
            self.fields.pop("confirm")
        else:
            self.fields.pop("reason")
        if not attestation_required:
            for field in ("declarant_name", "board_resolution_reference", "attest_officeholder"):
                self.fields.pop(field)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "acn",
        "company_type",
        "status_badge",
        "is_open_to_investors",
        "owner_email",
        "city",
        "state",
        "created_at",
    ]
    list_filter = ["status", "is_open_to_investors", "company_type", "state", "created_at"]
    search_fields = ["name", "trading_name", "acn", "abn", "owner__email"]
    readonly_fields = [
        "status",
        "registry_status",
        "registry_reason",
        "registry_checked_at",
        "registry_entity_name",
        "registry_entity_status",
        "officeholder_attested_by",
        "officeholder_attested_at",
        "officeholder_attestation",
        "info_request_reason",
        "rejection_reason",
        "warning_reason",
        "suspension_reason",
        "delisting_reason",
        "withdrawal_reason",
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
        "additional_info_response",
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
                    "is_open_to_investors",
                ],
                "description": (
                    "The owner opts a company into the investor directory; clearing this box takes it out "
                    "again and no company is listed until its owner opts in."
                ),
            },
        ),
        (
            "Registry and officeholder review",
            {
                "fields": [
                    "registry_status",
                    "registry_reason",
                    "registry_checked_at",
                    "registry_entity_name",
                    "registry_entity_status",
                    "declarant_name",
                    "board_resolution_reference",
                    "officeholder_attested_by",
                    "officeholder_attested_at",
                    "officeholder_attestation",
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
                    "additional_info_response",
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
            "Token Operations",
            {
                "fields": ["operator_wallet"],
                "description": (
                    "Issuer wallet recorded on share-token deployments: one of the owner's verified EVM wallets "
                    "(set it after the company exists, the add form offers none)."
                ),
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

    inlines = [CompanyDocumentInline, CompanyRegistryCheckInline]

    actions = ["start_review_action"]

    status_badge = status_badge(STATUS_COLORS)

    def get_urls(self):
        custom_urls = [
            admin_action_re_path(
                self,
                rf"^(?P<uuid>[0-9a-f-]+)/(?P<action>{'|'.join(TRANSITIONS)})/$",
                "companies_company_transition",
                self.transition_view,
            ),
        ]
        return custom_urls + super().get_urls()

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is None:
            return readonly

        readonly.append("owner")
        if obj.status != CompanyStatus.DRAFT:
            readonly.extend(IMMUTABLE_AFTER_DRAFT)
        if obj.status not in (CompanyStatus.DRAFT, CompanyStatus.INFO_REQUIRED):
            readonly.extend(["name", "declarant_name", "board_resolution_reference"])
        return readonly

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        match = getattr(request, "resolver_match", None)
        if request.method == "POST" and match and match.url_name == "companies_company_change":
            return queryset.select_for_update()
        return queryset

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        update_company(
            obj, {field: form.cleaned_data[field] for field in form.changed_data if field in EDITABLE_FIELDS}
        )
        obj.refresh_from_db()

    def get_form(self, request, obj=None, **kwargs):
        request._operator_wallet_owner = obj.owner if obj is not None else None
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "operator_wallet":
            owner = getattr(request, "_operator_wallet_owner", None)
            kwargs["queryset"] = Wallet.objects.visible_to_user(owner).verified_evm().select_related("user_account")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def owner_email(self, obj):
        return obj.email

    owner_email.short_description = "Email"
    owner_email.admin_order_field = "owner__email"

    def _action_url(self, obj, slug):
        if slug is None:
            return None
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

    def transition_view(self, request, company, action):
        spec = TRANSITIONS[action]
        change_url = reverse("admin:companies_company_change", args=[company.pk])
        attestation_required = action == "approve" or (
            action in ("activate", "resolve-warning", "reinstate") and not company.has_officeholder_attestation
        )
        form = TransitionForm(
            request.POST if request.method == "POST" else None,
            spec=spec,
            attestation_required=attestation_required,
            initial={
                "declarant_name": company.declarant_name,
                "board_resolution_reference": company.board_resolution_reference,
            },
        )
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
                "registry_checks": company.registry_checks.all(),
            }
            return render(request, "admin/companies/company/transition_form.html", context)
        kwargs = {spec["actor"]: request.user} if "actor" in spec else {}
        if "reason" in form.cleaned_data:
            kwargs["reason"] = form.cleaned_data["reason"]
        declaration = {
            key: form.cleaned_data[key]
            for key in ("declarant_name", "board_resolution_reference", "attest_officeholder")
            if key in form.cleaned_data
        }

        try:
            company = transition_company(company, spec["method"], actor=request.user, declaration=declaration, **kwargs)
        except APIException as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.add_message(request, spec.get("level", messages.SUCCESS), spec["done"].format(name=company.name))
        return HttpResponseRedirect(change_url)

    @admin.action(description="Start review for selected submitted applications")
    def start_review_action(self, request, queryset):
        count = 0
        for company in queryset.filter(status=CompanyStatus.SUBMITTED):
            transition_company(company, "start_review", actor=request.user)
            count += 1
        self.message_user(request, f"Review started for {count} applications.")
