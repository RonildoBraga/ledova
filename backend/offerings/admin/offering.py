from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import re_path, reverse

from offerings.exceptions import InvalidOfferingTransitionException
from offerings.models import Offering, OfferingStatus
from offerings.services import transition_offering, unissued_headroom
from shared.utils.admin_display import action_buttons
from tokens.admin._helpers import status_badge
from tokens.admin.review_workflow import ApproveForm, RejectForm

STATUS_COLORS = {
    OfferingStatus.DRAFT: "#6c757d",
    OfferingStatus.SUBMITTED: "#17a2b8",
    OfferingStatus.UNDER_REVIEW: "#007bff",
    OfferingStatus.APPROVED: "#28a745",
    OfferingStatus.REJECTED: "#dc3545",
    OfferingStatus.CLOSED: "#343a40",
    OfferingStatus.WITHDRAWN: "#adb5bd",
}

TRANSITIONS = {
    "start-review": dict(
        method="start_review",
        actor="reviewed_by",
        title="Start Review",
        alert="info",
        heading="Offering Review",
        intro="You are starting the review of this offering. The issuer is notified that the review has begun.",
        done="Review started.",
    ),
    "approve": dict(
        method="approve",
        actor="reviewed_by",
        form="approve",
        field="notes",
        title="Approve Offering",
        alert="success",
        heading="Offering Approval",
        intro=(
            "Approving publishes this offering to eligible investors from its opening time. It does not close "
            "when the cap is reached; closing stays a deliberate act."
        ),
        legend="Review Notes",
        button=("Approve Offering", "btn-success"),
        done="Offering approved.",
    ),
    "reject": dict(
        method="reject",
        actor="reviewed_by",
        form="reject",
        field="reason",
        title="Reject Offering",
        alert="warning",
        heading="Warning",
        intro="You are about to reject this offering. The issuer receives a notification carrying this reason.",
        legend="Rejection Reason",
        button=("Reject Offering", "btn-danger"),
        done="Offering rejected.",
        level=messages.WARNING,
    ),
    "close": dict(
        method="close",
        form="reject",
        field="reason",
        title="Close Offering",
        alert="danger",
        heading="Warning",
        intro=(
            "Closing stops this offering permanently. Close it once the cap is reached or the window has passed; "
            "nothing closes it automatically."
        ),
        legend="Closing Reason",
        button=("Close Offering", "btn-dark"),
        done="Offering closed.",
        level=messages.WARNING,
    ),
}

STATUS_BUTTONS = {
    OfferingStatus.DRAFT: [("Draft - Not Submitted", None, "#e9ecef", "#6c757d")],
    OfferingStatus.SUBMITTED: [
        ("▶ Start Review", "start-review", "#007bff"),
        ("✓ Approve", "approve", "#28a745"),
        ("✗ Reject", "reject", "#dc3545"),
    ],
    OfferingStatus.UNDER_REVIEW: [("✓ Approve", "approve", "#28a745"), ("✗ Reject", "reject", "#dc3545")],
    OfferingStatus.APPROVED: [("■ Close", "close", "#343a40")],
    OfferingStatus.REJECTED: [("Offering Rejected", None, "#e9ecef", "#6c757d")],
    OfferingStatus.CLOSED: [("Offering Closed", None, "#e9ecef", "#6c757d")],
    OfferingStatus.WITHDRAWN: [("Offering Withdrawn", None, "#e9ecef", "#6c757d")],
}


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display = [
        "token_symbol",
        "company_name",
        "status_badge",
        "price_per_share",
        "cap_shares",
        "opens_at",
        "closes_at",
        "created_at",
    ]
    list_filter = ["status", "exemption", "token__company"]
    search_fields = ["token__symbol", "token__name", "token__company__name", "summary"]
    list_select_related = ["token", "token__company"]
    ordering = ["-created_at"]
    filter_horizontal = ["settlement_assets", "documents"]
    readonly_fields = [
        "uuid",
        "status",
        "status_actions",
        "headroom",
        "is_open",
        "submitted_by",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "review_notes",
        "rejection_reason",
        "closed_at",
        "close_reason",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        ("Offering", {"fields": ["uuid", "token", "exemption", "summary", "use_of_proceeds"]}),
        ("Status & Actions", {"fields": ["status", "is_open", "headroom", "status_actions"]}),
        ("Price", {"fields": ["price_per_share", "price_currency"]}),
        ("Bounds", {"fields": ["minimum_shares", "target_shares", "cap_shares", "maximum_shares"]}),
        ("Window", {"fields": ["opens_at", "closes_at"]}),
        ("Payment Rails", {"fields": ["accepts_bank_transfer", "settlement_assets"]}),
        ("Documents", {"fields": ["documents"], "classes": ["collapse"]}),
        (
            "Review",
            {
                "fields": [
                    "submitted_by",
                    "submitted_at",
                    "reviewed_by",
                    "reviewed_at",
                    "review_notes",
                    "rejection_reason",
                    "closed_at",
                    "close_reason",
                ],
                "classes": ["collapse"],
            },
        ),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    status_badge = status_badge(STATUS_COLORS)

    def has_add_permission(self, request):
        return False

    @admin.display(description="Token", ordering="token__symbol")
    def token_symbol(self, obj):
        return obj.token.symbol

    @admin.display(description="Company", ordering="token__company__name")
    def company_name(self, obj):
        return obj.token.company.display_name

    @admin.display(description="Unissued headroom")
    def headroom(self, obj):
        if obj.pk is None:
            return "-"
        room = unissued_headroom(obj)
        return (
            f"{room['headroom']} shares ({room['authorized']} authorized, {room['issued']} issued, "
            f"{room['reserved']} reserved by other live offerings)"
        )

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
        return reverse("admin:offerings_offering_transition", args=[obj.uuid, slug])

    def get_urls(self):
        custom_urls = [
            re_path(
                rf"^(?P<uuid>[0-9a-f-]+)/(?P<action>{'|'.join(TRANSITIONS)})/$",
                self.admin_site.admin_view(self.transition_view),
                name="offerings_offering_transition",
            ),
        ]
        return custom_urls + super().get_urls()

    def _build_form(self, request, spec):
        if spec.get("form") == "approve":
            return ApproveForm(request.POST or None)
        return RejectForm(request.POST or None)

    def transition_view(self, request, uuid, action):
        offering = get_object_or_404(Offering, uuid=uuid)
        spec = TRANSITIONS[action]
        change_url = reverse("admin:offerings_offering_change", args=[offering.pk])
        kwargs = {spec["actor"]: request.user} if "actor" in spec else {}

        if "form" in spec:
            form = self._build_form(request, spec)
            if request.method != "POST" or not form.is_valid():
                context = {
                    **self.admin_site.each_context(request),
                    "title": f"{spec['title']}: {offering.token.symbol}",
                    "subtitle": None,
                    "opts": self.opts,
                    "offering": offering,
                    "headroom": self.headroom(offering),
                    "form": form,
                    "transition": spec,
                }
                return render(request, "admin/offerings/offering/transition_form.html", context)
            kwargs[spec["field"]] = form.cleaned_data[spec["field"]]

        try:
            transition_offering(offering, spec["method"], **kwargs)
        except InvalidOfferingTransitionException as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.add_message(request, spec.get("level", messages.SUCCESS), spec["done"])
        return HttpResponseRedirect(change_url)
