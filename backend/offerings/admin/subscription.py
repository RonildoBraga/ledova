from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import re_path, reverse

from offerings.exceptions import (
    InvalidSubscriptionTransitionException,
    SubscriptionRefusedException,
)
from offerings.models import SettlementRail, Subscription, SubscriptionStatus
from offerings.services.payments import normalize_reference
from offerings.services.subscription import (
    accept,
    allot_batch,
    confirm_payment,
    issue_instruction,
    record_refund,
    reject,
    retry_allotment,
    scale_back,
)
from operators.exceptions import SettlementAssetNotDeployedException
from shared.utils.admin_display import action_buttons
from tokens.admin._helpers import short_hex, status_badge
from users.exceptions import InvestorNotEligibleException

EMPTY_WHITELIST_RESULT = {"added": 0, "synced": 0, "skipped": 0, "errors": []}

REFUSALS = (
    SubscriptionRefusedException,
    InvalidSubscriptionTransitionException,
    InvestorNotEligibleException,
    SettlementAssetNotDeployedException,
)

STATUS_COLORS = {
    SubscriptionStatus.DRAFT: "#6c757d",
    SubscriptionStatus.SUBMITTED: "#17a2b8",
    SubscriptionStatus.ACCEPTED: "#007bff",
    SubscriptionStatus.AWAITING_PAYMENT: "#fd7e14",
    SubscriptionStatus.PAID: "#20c997",
    SubscriptionStatus.ALLOTTED: "#28a745",
    SubscriptionStatus.REJECTED: "#dc3545",
    SubscriptionStatus.WITHDRAWN: "#adb5bd",
    SubscriptionStatus.REFUNDED: "#6f42c1",
}

STATUS_BUTTONS = {
    SubscriptionStatus.DRAFT: [("Draft - Not Submitted", None, "#e9ecef", "#6c757d")],
    SubscriptionStatus.SUBMITTED: [
        ("✓ Accept and issue instruction", "accept", "#28a745"),
        ("✗ Reject", "reject", "#dc3545"),
    ],
    SubscriptionStatus.ACCEPTED: [
        ("▶ Issue payment instruction", "accept", "#007bff"),
        ("✗ Reject", "reject", "#dc3545"),
    ],
    SubscriptionStatus.AWAITING_PAYMENT: [
        ("$ Confirm payment", "confirm-payment", "#fd7e14"),
        ("↩ Record refund", "refund", "#6f42c1"),
        ("✗ Reject", "reject", "#dc3545"),
    ],
    SubscriptionStatus.PAID: [
        ("$ Confirm payment", "confirm-payment", "#fd7e14"),
        ("↻ Retry allotment", "retry", "#17a2b8"),
        ("↩ Record refund", "refund", "#6f42c1"),
    ],
    SubscriptionStatus.ALLOTTED: [("Allotted", None, "#e9ecef", "#6c757d")],
    SubscriptionStatus.REJECTED: [("Subscription Rejected", None, "#e9ecef", "#6c757d")],
    SubscriptionStatus.WITHDRAWN: [("Subscription Withdrawn", None, "#e9ecef", "#6c757d")],
    SubscriptionStatus.REFUNDED: [("✗ Reject", "reject", "#dc3545")],
}


class AcceptAndIssueForm(forms.Form):

    settlement_rail = forms.ChoiceField(choices=SettlementRail.choices, label="Settlement Rail")
    settlement_asset = forms.ModelChoiceField(queryset=None, required=False, label="Settlement Stablecoin")
    payment_due_at = forms.DateTimeField(required=False, label="Payment Due (optional)")

    def __init__(self, *args, offering, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["settlement_asset"].queryset = offering.settlement_assets.all()


class ConfirmPaymentForm(forms.Form):

    amount_received = forms.DecimalField(max_digits=18, decimal_places=2, label="Amount Received (AUD)")
    payment_received_on = forms.DateField(label="Date Received", widget=forms.DateInput(attrs={"type": "date"}))
    payment_reference_seen = forms.CharField(max_length=140, required=False, label="Reference On The Statement")
    payment_tx_hash = forms.CharField(max_length=66, required=False, label="Transfer Hash (stablecoin rail)")
    accept_as_final = forms.BooleanField(
        required=False,
        label="Accept as the final payment",
        help_text="Scales the allotment down to the whole shares the money covers and records the residual "
        "as a refund owed. Leave it clear to keep the subscription awaiting the balance.",
    )
    payment_notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Notes")


class RefundForm(forms.Form):

    refund_amount = forms.DecimalField(max_digits=18, decimal_places=2, label="Refund Amount (AUD)")
    refund_reference = forms.CharField(max_length=140, required=False, label="Refund Reference")
    payment_notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Notes")


class RejectSubscriptionForm(forms.Form):

    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=True, label="Reason")


ACTIONS = {
    "accept": dict(
        form=AcceptAndIssueForm,
        title="Accept And Issue",
        alert="success",
        heading="Acceptance",
        intro=(
            "Accepting re-runs the eligibility check against this account, because a certificate can lapse between "
            "submission and acceptance and the law cares about status at acceptance. The payment instruction is "
            "issued in the same click."
        ),
        legend="Payment Instruction",
        button=("Accept And Issue", "btn-success"),
        done="Accepted; the payment instruction is issued.",
    ),
    "confirm-payment": dict(
        form=ConfirmPaymentForm,
        title="Confirm Payment",
        alert="info",
        heading="Payment Confirmation",
        intro=(
            "Record the money that actually arrived. Equal to the amount due moves the subscription to paid; more "
            "records the overpayment as a refund owed; less keeps it awaiting the balance unless you accept it as "
            "final. A transfer hash can fund one subscription only."
        ),
        legend="Money Received",
        button=("Confirm Payment", "btn-success"),
        done="Payment confirmed.",
    ),
    "refund": dict(
        form=RefundForm,
        title="Record Refund",
        alert="warning",
        heading="Refund",
        intro=(
            "Record money sent back to the investor. The subscription is unwound with nothing allotted, and only "
            "then can it be rejected or withdrawn."
        ),
        legend="Refund",
        button=("Record Refund", "btn-dark"),
        done="Refund recorded.",
        level=messages.WARNING,
    ),
    "reject": dict(
        form=RejectSubscriptionForm,
        title="Reject Subscription",
        alert="danger",
        heading="Warning",
        intro=(
            "Rejecting closes this subscription. It is refused while money is recorded against it: refund it first."
        ),
        legend="Reason",
        button=("Reject Subscription", "btn-danger"),
        done="Subscription rejected.",
        level=messages.WARNING,
    ),
    "retry": dict(
        title="Retry Allotment",
        alert="info",
        heading="Retry",
        intro="Re-runs the mint for the issuance request already linked to this subscription. It never mints twice.",
        legend="Retry",
        button=("Retry Allotment", "btn-info"),
        done="Allotment retried; the task is running in the background.",
    ),
}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):

    list_display = [
        "reference_or_uuid",
        "offering_symbol",
        "investor",
        "quantity",
        "allotted_quantity",
        "amount_due",
        "amount_received",
        "status_badge",
        "tx_hash_short",
        "created_at",
    ]
    list_filter = ["status", "settlement_rail", "offering__token__company"]
    search_fields = ["reference", "payment_reference_seen", "payment_tx_hash", "wallet__address"]
    list_select_related = ["offering", "offering__token", "user_account", "wallet"]
    ordering = ["-created_at"]
    actions = ["allot_selected", "scale_back_selected", "whitelist_wallets"]
    readonly_fields = [
        "uuid",
        "status",
        "status_actions",
        "offering",
        "user_account",
        "wallet",
        "submitted_by",
        "quantity",
        "allotted_quantity",
        "price_per_share",
        "amount_due",
        "settlement_rail",
        "settlement_asset",
        "settlement_amount",
        "reference",
        "payment_instruction_issued_at",
        "payment_due_at",
        "amount_received",
        "payment_received_on",
        "payment_reference_seen",
        "payment_tx_hash",
        "payment_confirmed_by",
        "payment_confirmed_at",
        "payment_notes",
        "refund_amount",
        "refunded_at",
        "refund_reference",
        "issuance_request",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        ("Subscription", {"fields": ["uuid", "offering", "user_account", "wallet", "submitted_by"]}),
        ("Status & Actions", {"fields": ["status", "status_actions"]}),
        ("Shares", {"fields": ["quantity", "allotted_quantity", "price_per_share", "amount_due"]}),
        (
            "Payment Instruction",
            {
                "fields": [
                    "settlement_rail",
                    "settlement_asset",
                    "settlement_amount",
                    "reference",
                    "payment_instruction_issued_at",
                    "payment_due_at",
                ]
            },
        ),
        (
            "Payment Received",
            {
                "fields": [
                    "amount_received",
                    "payment_received_on",
                    "payment_reference_seen",
                    "payment_tx_hash",
                    "payment_confirmed_by",
                    "payment_confirmed_at",
                    "payment_notes",
                ]
            },
        ),
        ("Refund", {"fields": ["refund_amount", "refunded_at", "refund_reference"], "classes": ["collapse"]}),
        ("Allotment", {"fields": ["issuance_request"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    status_badge = status_badge(STATUS_COLORS)

    def has_add_permission(self, request):
        return False

    def get_search_results(self, request, queryset, search_term):
        results, duplicates = super().get_search_results(request, queryset, search_term)
        normalized = normalize_reference(search_term)
        if normalized:
            results = results | queryset.filter(reference=normalized)
        return results, duplicates

    @admin.display(description="Reference", ordering="reference")
    def reference_or_uuid(self, obj):
        return obj.reference or f"{obj.uuid}"[:8]

    @admin.display(description="Offering", ordering="offering__token__symbol")
    def offering_symbol(self, obj):
        return obj.offering.token.symbol

    @admin.display(description="Investor", ordering="user_account__account_number")
    def investor(self, obj):
        return obj.user_account.account_number

    @admin.display(description="Transfer")
    def tx_hash_short(self, obj):
        return short_hex(obj.payment_tx_hash)

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
        return reverse("admin:offerings_subscription_action", args=[obj.uuid, slug])

    def get_urls(self):
        custom_urls = [
            re_path(
                rf"^(?P<uuid>[0-9a-f-]+)/(?P<action>{'|'.join(ACTIONS)})/$",
                self.admin_site.admin_view(self.action_view),
                name="offerings_subscription_action",
            ),
        ]
        return custom_urls + super().get_urls()

    def action_view(self, request, uuid, action):
        subscription = get_object_or_404(Subscription.objects.with_relations(), uuid=uuid)
        spec = ACTIONS[action]
        change_url = reverse("admin:offerings_subscription_change", args=[subscription.pk])
        form = self._build_form(request, spec, subscription)

        if form is not None and (request.method != "POST" or not form.is_valid()):
            return self._render(request, subscription, spec, form)
        if form is None and request.method != "POST":
            return self._render(request, subscription, spec, form)

        data = form.cleaned_data if form is not None else {}
        try:
            RUNNERS[action](subscription, request, data)
        except REFUSALS as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.add_message(request, spec.get("level", messages.SUCCESS), spec["done"])
        return HttpResponseRedirect(change_url)

    @staticmethod
    def _build_form(request, spec, subscription):
        form_class = spec.get("form")
        if form_class is None:
            return None
        if form_class is AcceptAndIssueForm:
            return form_class(request.POST or None, offering=subscription.offering)
        return form_class(request.POST or None)

    def _render(self, request, subscription, spec, form):
        context = {
            **self.admin_site.each_context(request),
            "title": f"{spec['title']}: {subscription.offering.token.symbol}",
            "subtitle": None,
            "opts": self.opts,
            "subscription": subscription,
            "form": form,
            "transition": spec,
        }
        return render(request, "admin/offerings/subscription/action_form.html", context)

    @admin.action(description="Allot selected subscriptions")
    def allot_selected(self, request, queryset):
        result = allot_batch(list(queryset.with_relations()), request.user)
        if result["allotted"]:
            self.message_user(request, f"Allotted {result['allotted']} subscription(s).", messages.SUCCESS)
        for refusal in result["refusals"]:
            self.message_user(request, refusal, messages.ERROR)
        if not result["allotted"] and not result["refusals"]:
            self.message_user(request, "Nothing to allot in that selection.", messages.WARNING)

    @admin.action(description="Scale back the offerings of the selected subscriptions")
    def scale_back_selected(self, request, queryset):
        offerings = {row.offering_id: row.offering for row in queryset.select_related("offering", "offering__token")}
        for offering in offerings.values():
            result = scale_back(offering)
            self.message_user(
                request,
                f"{offering.token.symbol}: {result['scaled']} subscription(s) scaled; "
                f"{result['requested']} shares requested against {result['room']} available.",
                messages.SUCCESS if result["scaled"] else messages.INFO,
            )

    @admin.action(description="Whitelist the wallets of the selected subscriptions")
    def whitelist_wallets(self, request, queryset):
        from whitelist.models import WhitelistEntry
        from whitelist.services import WhitelistService

        wallet_ids = {subscription.wallet_id for subscription in queryset}
        entries = list(WhitelistEntry.objects.filter(wallet_id__in=wallet_ids))
        missing = wallet_ids - {entry.wallet_id for entry in entries}
        result = WhitelistService().ensure_whitelisted(entries) if entries else EMPTY_WHITELIST_RESULT
        if result["added"] or result["synced"]:
            self.message_user(
                request, f"Whitelisted {result['added']} and synced {result['synced']} address(es).", messages.SUCCESS
            )
        if result["skipped"]:
            self.message_user(request, f"Skipped {result['skipped']} already whitelisted.", messages.WARNING)
        if missing:
            self.message_user(
                request, f"{len(missing)} wallet(s) have no whitelist entry; add them first.", messages.ERROR
            )
        for error in result["errors"]:
            self.message_user(request, error, messages.ERROR)


def _run_accept(subscription, request, data):
    if subscription.status == SubscriptionStatus.SUBMITTED:
        accept(subscription)
    issue_instruction(
        subscription,
        rail=data["settlement_rail"],
        settlement_asset=data.get("settlement_asset"),
        due_at=data.get("payment_due_at"),
    )


def _run_confirm_payment(subscription, request, data):
    confirm_payment(
        subscription,
        confirmed_by=request.user,
        amount_received=Decimal(data["amount_received"]),
        received_on=data["payment_received_on"],
        reference_seen=data.get("payment_reference_seen") or "",
        tx_hash=data.get("payment_tx_hash") or "",
        notes=data.get("payment_notes") or "",
        accept_as_final=bool(data.get("accept_as_final")),
    )


def _run_refund(subscription, request, data):
    record_refund(
        subscription,
        amount=Decimal(data["refund_amount"]),
        reference=data.get("refund_reference") or "",
        notes=data.get("payment_notes") or "",
    )


RUNNERS = {
    "accept": _run_accept,
    "confirm-payment": _run_confirm_payment,
    "refund": _run_refund,
    "reject": lambda subscription, request, data: reject(subscription, reason=data["reason"]),
    "retry": lambda subscription, request, data: retry_allotment(subscription, request.user),
}
