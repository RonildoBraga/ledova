from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from companies.models import (
    ApplicationReview,
    Company,
    CompanyDocument,
    CompanyStatus,
)

User = get_user_model()


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


class RequestInfoForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        label="Information Requested",
        help_text="Describe what additional information is needed from the company.",
    )


class RejectCompanyForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        label="Rejection Reason",
        help_text="Provide a clear reason for rejecting this company application.",
    )


class SuspendCompanyForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        label="Suspension Reason",
        help_text="Provide a reason for suspending this company.",
    )


class WarningForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        label="Warning Reason",
        help_text="Describe the compliance issue.",
    )


class DelistForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        label="Delisting Reason",
        help_text="Provide a reason for permanently delisting this company.",
    )


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

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:uuid>/start-review/",
                self.admin_site.admin_view(self.start_review_view),
                name="companies_company_start_review",
            ),
            path(
                "<uuid:uuid>/request-info/",
                self.admin_site.admin_view(self.request_info_view),
                name="companies_company_request_info",
            ),
            path(
                "<uuid:uuid>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="companies_company_approve",
            ),
            path(
                "<uuid:uuid>/activate/",
                self.admin_site.admin_view(self.activate_view),
                name="companies_company_activate",
            ),
            path(
                "<uuid:uuid>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="companies_company_reject",
            ),
            path(
                "<uuid:uuid>/issue-warning/",
                self.admin_site.admin_view(self.issue_warning_view),
                name="companies_company_issue_warning",
            ),
            path(
                "<uuid:uuid>/resolve-warning/",
                self.admin_site.admin_view(self.resolve_warning_view),
                name="companies_company_resolve_warning",
            ),
            path(
                "<uuid:uuid>/suspend/",
                self.admin_site.admin_view(self.suspend_view),
                name="companies_company_suspend",
            ),
            path(
                "<uuid:uuid>/reinstate/",
                self.admin_site.admin_view(self.reinstate_view),
                name="companies_company_reinstate",
            ),
            path(
                "<uuid:uuid>/delist/",
                self.admin_site.admin_view(self.delist_view),
                name="companies_company_delist",
            ),
            path(
                "<uuid:uuid>/assign-reviewers/",
                self.admin_site.admin_view(self.assign_reviewers_view),
                name="companies_company_assign_reviewers",
            ),
        ]
        return custom_urls + urls

    def status_badge(self, obj):
        colors = {
            CompanyStatus.DRAFT: "#6c757d",
            CompanyStatus.SUBMITTED: "#17a2b8",
            CompanyStatus.REVIEW: "#007bff",
            CompanyStatus.INFO_REQUIRED: "#fd7e14",
            CompanyStatus.APPROVED: "#20c997",
            CompanyStatus.ACTIVE: "#28a745",
            CompanyStatus.WARNING: "#ffc107",
            CompanyStatus.SUSPENDED: "#dc3545",
            CompanyStatus.DELISTED: "#343a40",
            CompanyStatus.REJECTED: "#6c757d",
            CompanyStatus.WITHDRAWN: "#adb5bd",
        }
        color = colors.get(obj.status, "#777777")
        text_color = "black" if obj.status == CompanyStatus.WARNING else "white"
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            text_color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def owner_email(self, obj):
        return obj.email

    owner_email.short_description = "Email"
    owner_email.admin_order_field = "owner__email"

    def status_actions(self, obj):
        if obj.pk is None:
            return "-"

        buttons = []
        base_style = (
            "display: inline-block; padding: 6px 12px; margin: 2px; "
            "text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;"
        )

        if obj.status == CompanyStatus.SUBMITTED:
            assign_reviewers_url = reverse("admin:companies_company_assign_reviewers", args=[obj.uuid])
            start_review_url = reverse("admin:companies_company_start_review", args=[obj.uuid])
            reject_url = reverse("admin:companies_company_reject", args=[obj.uuid])
            buttons.append(
                f'<a href="{assign_reviewers_url}" style="{base_style} background-color: #6f42c1; color: white;">'
                "👥 Assign Reviewers</a>"
            )
            buttons.append(
                f'<a href="{start_review_url}" style="{base_style} background-color: #007bff; color: white;">'
                "▶ Start Review</a>"
            )
            buttons.append(
                f'<a href="{reject_url}" style="{base_style} background-color: #dc3545; color: white;">' "✗ Reject</a>"
            )

        elif obj.status == CompanyStatus.REVIEW:
            assign_reviewers_url = reverse("admin:companies_company_assign_reviewers", args=[obj.uuid])
            request_info_url = reverse("admin:companies_company_request_info", args=[obj.uuid])
            approve_url = reverse("admin:companies_company_approve", args=[obj.uuid])
            reject_url = reverse("admin:companies_company_reject", args=[obj.uuid])
            buttons.append(
                f'<a href="{assign_reviewers_url}" style="{base_style} background-color: #6f42c1; color: white;">'
                "👥 Assign Reviewers</a>"
            )
            buttons.append(
                f'<a href="{request_info_url}" style="{base_style} background-color: #fd7e14; color: white;">'
                "? Request Info</a>"
            )
            buttons.append(
                f'<a href="{approve_url}" style="{base_style} background-color: #20c997; color: white;">'
                "✓ Approve</a>"
            )
            buttons.append(
                f'<a href="{reject_url}" style="{base_style} background-color: #dc3545; color: white;">' "✗ Reject</a>"
            )

        elif obj.status == CompanyStatus.INFO_REQUIRED:
            buttons.append(
                f'<span style="{base_style} background-color: #fd7e14; color: white;">' "⏳ Awaiting Response</span>"
            )

        elif obj.status == CompanyStatus.APPROVED:
            activate_url = reverse("admin:companies_company_activate", args=[obj.uuid])
            buttons.append(
                f'<a href="{activate_url}" style="{base_style} background-color: #28a745; color: white;">'
                "✓ Activate Company</a>"
            )

        elif obj.status == CompanyStatus.ACTIVE:
            warning_url = reverse("admin:companies_company_issue_warning", args=[obj.uuid])
            suspend_url = reverse("admin:companies_company_suspend", args=[obj.uuid])
            delist_url = reverse("admin:companies_company_delist", args=[obj.uuid])
            buttons.append(
                f'<a href="{warning_url}" style="{base_style} background-color: #ffc107; color: black;">'
                "⚠ Issue Warning</a>"
            )
            buttons.append(
                f'<a href="{suspend_url}" style="{base_style} background-color: #dc3545; color: white;">'
                "⏸ Suspend</a>"
            )
            buttons.append(
                f'<a href="{delist_url}" style="{base_style} background-color: #343a40; color: white;">' "✗ Delist</a>"
            )

        elif obj.status == CompanyStatus.WARNING:
            resolve_url = reverse("admin:companies_company_resolve_warning", args=[obj.uuid])
            suspend_url = reverse("admin:companies_company_suspend", args=[obj.uuid])
            delist_url = reverse("admin:companies_company_delist", args=[obj.uuid])
            buttons.append(
                f'<a href="{resolve_url}" style="{base_style} background-color: #28a745; color: white;">'
                "✓ Resolve Warning</a>"
            )
            buttons.append(
                f'<a href="{suspend_url}" style="{base_style} background-color: #dc3545; color: white;">'
                "⏸ Suspend</a>"
            )
            buttons.append(
                f'<a href="{delist_url}" style="{base_style} background-color: #343a40; color: white;">' "✗ Delist</a>"
            )

        elif obj.status == CompanyStatus.SUSPENDED:
            reinstate_url = reverse("admin:companies_company_reinstate", args=[obj.uuid])
            delist_url = reverse("admin:companies_company_delist", args=[obj.uuid])
            buttons.append(
                f'<a href="{reinstate_url}" style="{base_style} background-color: #28a745; color: white;">'
                "↻ Reinstate</a>"
            )
            buttons.append(
                f'<a href="{delist_url}" style="{base_style} background-color: #343a40; color: white;">' "✗ Delist</a>"
            )

        elif obj.status in [
            CompanyStatus.DRAFT,
            CompanyStatus.REJECTED,
            CompanyStatus.WITHDRAWN,
            CompanyStatus.DELISTED,
        ]:
            status_labels = {
                CompanyStatus.DRAFT: "Draft - Not Submitted",
                CompanyStatus.REJECTED: "Application Rejected",
                CompanyStatus.WITHDRAWN: "Application Withdrawn",
                CompanyStatus.DELISTED: "Permanently Delisted",
            }
            buttons.append(
                f'<span style="{base_style} background-color: #e9ecef; color: #6c757d;">'
                f"{status_labels.get(obj.status, obj.get_status_display())}</span>"
            )

        if not buttons:
            return "-"

        return mark_safe(" ".join(buttons))

    status_actions.short_description = "Quick Actions"

    def start_review_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.SUBMITTED:
            messages.error(request, f"Cannot start review: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        company.start_review()
        messages.success(request, f"Review started for '{company.name}'.")
        return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

    def request_info_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.REVIEW:
            messages.error(request, f"Cannot request info: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        if request.method == "POST":
            form = RequestInfoForm(request.POST)
            if form.is_valid():
                company.request_info(reason=form.cleaned_data["reason"])
                messages.success(request, f"Additional information requested from '{company.name}'.")
                return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))
        else:
            form = RequestInfoForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Request Information: {company.name}",
            "subtitle": None,
            "company": company,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/companies/company/request_info_form.html", context)

    def approve_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.REVIEW:
            messages.error(request, f"Cannot approve: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        company.approve(approved_by=request.user)
        messages.success(request, f"Company '{company.name}' has been approved.")
        return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

    def activate_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.APPROVED:
            messages.error(request, f"Cannot activate: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        company.activate()
        messages.success(request, f"Company '{company.name}' is now active on the platform.")
        return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

    def reject_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status not in [CompanyStatus.SUBMITTED, CompanyStatus.REVIEW]:
            messages.error(request, f"Cannot reject: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        if request.method == "POST":
            form = RejectCompanyForm(request.POST)
            if form.is_valid():
                company.reject(reason=form.cleaned_data["reason"], rejected_by=request.user)
                messages.success(request, f"Company '{company.name}' application has been rejected.")
                return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))
        else:
            form = RejectCompanyForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Reject Application: {company.name}",
            "subtitle": None,
            "company": company,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/companies/company/reject_form.html", context)

    def issue_warning_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.ACTIVE:
            messages.error(request, f"Cannot issue warning: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        if request.method == "POST":
            form = WarningForm(request.POST)
            if form.is_valid():
                company.issue_warning(reason=form.cleaned_data["reason"])
                messages.warning(request, f"Warning issued to '{company.name}'.")
                return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))
        else:
            form = WarningForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Issue Warning: {company.name}",
            "subtitle": None,
            "company": company,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/companies/company/warning_form.html", context)

    def resolve_warning_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.WARNING:
            messages.error(request, f"Cannot resolve warning: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        company.resolve_warning()
        messages.success(request, f"Warning resolved for '{company.name}'. Company is now active.")
        return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

    def suspend_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status not in [CompanyStatus.ACTIVE, CompanyStatus.WARNING]:
            messages.error(request, f"Cannot suspend: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        if request.method == "POST":
            form = SuspendCompanyForm(request.POST)
            if form.is_valid():
                company.suspend(reason=form.cleaned_data["reason"])
                messages.warning(request, f"Company '{company.name}' has been suspended.")
                return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))
        else:
            form = SuspendCompanyForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Suspend Company: {company.name}",
            "subtitle": None,
            "company": company,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/companies/company/suspend_form.html", context)

    def reinstate_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status != CompanyStatus.SUSPENDED:
            messages.error(request, f"Cannot reinstate: status is '{company.get_status_display()}'")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        company.reinstate()
        messages.success(request, f"Company '{company.name}' has been reinstated and is now active.")
        return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

    def delist_view(self, request, uuid):
        company = get_object_or_404(Company, uuid=uuid)

        if company.status in [CompanyStatus.DRAFT, CompanyStatus.REJECTED, CompanyStatus.WITHDRAWN]:
            messages.error(request, "Cannot delist: company was never active")
            return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))

        if request.method == "POST":
            form = DelistForm(request.POST)
            if form.is_valid():
                company.delist(reason=form.cleaned_data["reason"])
                messages.error(request, f"Company '{company.name}' has been permanently delisted.")
                return HttpResponseRedirect(reverse("admin:companies_company_change", args=[company.pk]))
        else:
            form = DelistForm()

        context = {
            **self.admin_site.each_context(request),
            "title": f"Delist Company: {company.name}",
            "subtitle": None,
            "company": company,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/companies/company/delist_form.html", context)

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
