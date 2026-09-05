from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, re_path, reverse
from django.utils.html import format_html

from shared.views import stream_stored_file
from tokens.admin._helpers import action_buttons, status_badge
from users.exceptions import InvalidClassificationTransitionException
from users.models import InvestorClassification, InvestorClassificationStatus
from users.services import transition_classification

STATUS_COLORS = {
    InvestorClassificationStatus.SUBMITTED: "#17a2b8",
    InvestorClassificationStatus.VERIFIED: "#28a745",
    InvestorClassificationStatus.REJECTED: "#dc3545",
    InvestorClassificationStatus.REVOKED: "#343a40",
}


class VerifyForm(forms.Form):
    expires_at = forms.DateTimeField(
        label="Expires At",
        help_text="The claim stops counting from this moment. Two years from the certificate date by default.",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    notes = forms.CharField(
        required=False,
        label="Review Notes",
        help_text="What you checked, and against which document.",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
    )


class ReasonForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 4, "cols": 60}))

    def __init__(self, *args, label, help_text, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].label = label
        self.fields["reason"].help_text = help_text


TRANSITIONS = {
    "verify": dict(
        method="verify",
        form="verify",
        title="Verify Classification",
        alert="warning",
        heading="Wholesale Investor Verification",
        intro=(
            "You are confirming that the evidence attached to this claim supports it. The account can see and "
            "subscribe to offerings until the expiry you set here."
        ),
        legend="Verification Details",
        button=("Verify Classification", "btn-success"),
        done="Classification verified.",
    ),
    "reject": dict(
        method="reject",
        form="reason",
        title="Reject Classification",
        alert="warning",
        heading="Warning",
        intro=(
            "You are about to reject this wholesale investor claim. The account stays ineligible and can submit a "
            "fresh claim with better evidence."
        ),
        legend="Rejection Details",
        label="Rejection Reason",
        help="Say what the evidence failed to show.",
        button=("Reject Classification", "btn-danger"),
        done="Classification rejected.",
        level=messages.WARNING,
    ),
    "revoke": dict(
        method="revoke",
        form="reason",
        title="Revoke Classification",
        alert="danger",
        heading="Warning",
        intro=(
            "You are about to revoke a verified classification. The account becomes ineligible immediately and "
            "cannot subscribe to any offering until a fresh claim is verified."
        ),
        legend="Revocation Details",
        label="Revocation Reason",
        help="Say why the claim no longer holds.",
        button=("Revoke Classification", "btn-dark"),
        done="Classification revoked.",
        level=messages.WARNING,
    ),
}

STATUS_BUTTONS = {
    InvestorClassificationStatus.SUBMITTED: [
        ("✓ Verify", "verify", "#28a745"),
        ("✗ Reject", "reject", "#dc3545"),
    ],
    InvestorClassificationStatus.VERIFIED: [("⏸ Revoke", "revoke", "#343a40")],
    InvestorClassificationStatus.REJECTED: [("Claim Rejected", None, "#e9ecef", "#6c757d")],
    InvestorClassificationStatus.REVOKED: [("Claim Revoked", None, "#e9ecef", "#6c757d")],
}


@admin.register(InvestorClassification)
class InvestorClassificationAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
        "account_email",
        "category",
        "status_badge",
        "liveness",
        "expires_at",
        "created_at",
    ]
    list_filter = ["status", "category", "created_at"]
    search_fields = [
        "user_account__account_number",
        "user_account__user_profiles__user__email",
        "certifier_name",
        "certifier_membership_number",
    ]
    list_select_related = ["user_account", "company"]
    ordering = ["-created_at"]
    readonly_fields = [
        "uuid",
        "status",
        "declaration_text",
        "evidence_link",
        "evidence_file_size",
        "evidence_mime_type",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "review_notes",
        "rejection_reason",
        "expires_at",
        "liveness",
        "status_actions",
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        ("Claim", {"fields": ["uuid", "user_account", "company", "category", "declared_basis"]}),
        ("Status & Actions", {"fields": ["status", "liveness", "expires_at", "status_actions"]}),
        (
            "Declaration",
            {"fields": ["declaration_accepted", "declaration_text"], "classes": ["collapse"]},
        ),
        (
            "Evidence",
            {"fields": ["evidence_link", "evidence_file_size", "evidence_mime_type"]},
        ),
        (
            "Accountant's Certificate",
            {
                "fields": [
                    "certificate_issued_at",
                    "certifier_name",
                    "certifier_body",
                    "certifier_membership_number",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Review",
            {
                "fields": ["submitted_at", "reviewed_by", "reviewed_at", "review_notes", "rejection_reason"],
                "classes": ["collapse"],
            },
        ),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    status_badge = status_badge(STATUS_COLORS)

    @admin.display(description="Account")
    def account_email(self, obj):
        profile = obj.user_account.user_profiles.first()
        return profile.user.email if profile else obj.user_account.account_number

    @admin.display(description="Live")
    def liveness(self, obj):
        if obj.is_live:
            return "Live"
        if obj.is_expired:
            return "Expired"
        return "-"

    @admin.display(description="Evidence")
    def evidence_link(self, obj):
        if obj.pk is None or not obj.evidence_file:
            return "-"
        url = reverse("admin:users_investorclassification_evidence", args=[obj.uuid])
        return format_html('<a href="{}" target="_blank">Open evidence</a>', url)

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

    def _action_url(self, obj, slug):
        if slug is None:
            return None
        return reverse("admin:users_investorclassification_transition", args=[obj.uuid, slug])

    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:uuid>/evidence/",
                self.admin_site.admin_view(self.evidence_view),
                name="users_investorclassification_evidence",
            ),
            re_path(
                rf"^(?P<uuid>[0-9a-f-]+)/(?P<action>{'|'.join(TRANSITIONS)})/$",
                self.admin_site.admin_view(self.transition_view),
                name="users_investorclassification_transition",
            ),
        ]
        return custom_urls + super().get_urls()

    def evidence_view(self, request, uuid):
        classification = get_object_or_404(InvestorClassification, uuid=uuid)
        return stream_stored_file(classification.evidence_file, classification.evidence_mime_type)

    def _build_form(self, request, classification, spec):
        if spec["form"] == "verify":
            return VerifyForm(request.POST or None, initial={"expires_at": classification.default_expiry})
        return ReasonForm(request.POST or None, label=spec["label"], help_text=spec["help"])

    def transition_view(self, request, uuid, action):
        classification = get_object_or_404(InvestorClassification, uuid=uuid)
        spec = TRANSITIONS[action]
        change_url = reverse("admin:users_investorclassification_change", args=[classification.pk])
        form = self._build_form(request, classification, spec)

        if request.method != "POST" or not form.is_valid():
            context = {
                **self.admin_site.each_context(request),
                "title": f"{spec['title']}: {classification.uuid}",
                "subtitle": None,
                "opts": self.opts,
                "classification": classification,
                "form": form,
                "transition": spec,
                "intro": spec["intro"],
            }
            return render(request, "admin/users/investorclassification/transition_form.html", context)

        kwargs = {"reviewed_by": request.user, **form.cleaned_data}
        try:
            transition_classification(classification, spec["method"], **kwargs)
        except InvalidClassificationTransitionException as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.add_message(request, spec.get("level", messages.SUCCESS), spec["done"])
        return HttpResponseRedirect(change_url)
