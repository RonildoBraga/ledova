from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from offerings.exceptions import (
    InvalidSubscriptionTransitionException,
    SubscriptionRefusedException,
)
from offerings.models.owner_column import DerivesCompanyFromOffering
from offerings.querysets.subscription import SubscriptionQuerySet
from operators.models import STABLECOIN_ONLY
from shared.models import BaseModel

MAX_REFERENCE_LENGTH = 18
ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
RAIL_ASSET_PAIRING_ERROR = "A bank transfer carries no settlement asset, and a stablecoin settlement must name one."
ALLOTTED_ABOVE_REQUESTED_ERROR = "A subscription cannot be allotted more shares than it asked for."
QUANTITY_POSITIVE_ERROR = "A subscription must ask for at least one share."
MONEY_ALREADY_IN = (
    "{amount} has already been received against {reference}. Record a refund before rejecting or withdrawing it; "
    "money that arrived cannot be waved away by a status change."
)


class SubscriptionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    ACCEPTED = "accepted", "Accepted"
    AWAITING_PAYMENT = "awaiting_payment", "Awaiting Payment"
    PAID = "paid", "Paid"
    ALLOTTED = "allotted", "Allotted"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"
    REFUNDED = "refunded", "Refunded"


class SettlementRail(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    STABLECOIN = "stablecoin", "Stablecoin"


OPEN_SUBSCRIPTION_STATUSES = [
    SubscriptionStatus.DRAFT,
    SubscriptionStatus.SUBMITTED,
    SubscriptionStatus.ACCEPTED,
    SubscriptionStatus.AWAITING_PAYMENT,
    SubscriptionStatus.PAID,
]

CLOSEABLE_SUBSCRIPTION_STATUSES = OPEN_SUBSCRIPTION_STATUSES + [SubscriptionStatus.REFUNDED]

REFUNDABLE_SUBSCRIPTION_STATUSES = [
    SubscriptionStatus.AWAITING_PAYMENT,
    SubscriptionStatus.PAID,
    SubscriptionStatus.ALLOTTED,
    SubscriptionStatus.REFUNDED,
]

REFUND_FIELDS = ["status", "refund_amount", "refund_reference", "refunded_at", "payment_notes", "updated_at"]


class Subscription(DerivesCompanyFromOffering, BaseModel):

    objects = SubscriptionQuerySet.as_manager()

    offering = models.ForeignKey("offerings.Offering", on_delete=models.PROTECT, related_name="subscriptions")

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "Owner, derived from offering.company and held directly so a " "row-level security policy can read it"
        ),
    )
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="subscriptions")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_subscriptions",
    )
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="subscriptions")

    quantity = models.PositiveIntegerField()
    allotted_quantity = models.PositiveIntegerField(null=True, blank=True)
    price_per_share = models.DecimalField(max_digits=18, decimal_places=2)
    amount_due = models.DecimalField(max_digits=18, decimal_places=2)

    settlement_rail = models.CharField(
        max_length=20, choices=SettlementRail.choices, default=SettlementRail.BANK_TRANSFER
    )
    settlement_asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subscriptions",
        limit_choices_to=STABLECOIN_ONLY,
    )
    settlement_amount = models.BigIntegerField(null=True, blank=True)

    reference = models.CharField(max_length=MAX_REFERENCE_LENGTH, blank=True)
    payment_instruction_issued_at = models.DateTimeField(null=True, blank=True)
    payment_due_at = models.DateTimeField(null=True, blank=True)

    amount_received = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    payment_received_on = models.DateField(null=True, blank=True)
    payment_reference_seen = models.CharField(max_length=140, blank=True)
    payment_tx_hash = models.CharField(max_length=66, blank=True)
    payment_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_subscriptions",
    )
    payment_confirmed_at = models.DateTimeField(null=True, blank=True)
    payment_notes = models.TextField(blank=True)

    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reference = models.CharField(max_length=140, blank=True)

    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.DRAFT)

    issuance_request = models.OneToOneField(
        "tokens.ShareIssuanceRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription",
    )

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["offering", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["reference"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["reference"],
                condition=~models.Q(reference=""),
                name="subscription_reference_unique",
            ),
            models.UniqueConstraint(
                Lower("payment_tx_hash"),
                condition=~models.Q(payment_tx_hash=""),
                name="subscription_payment_tx_hash_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="subscription_quantity_positive",
                violation_error_message=QUANTITY_POSITIVE_ERROR,
            ),
            models.CheckConstraint(
                condition=models.Q(allotted_quantity__isnull=True)
                | models.Q(allotted_quantity__lte=models.F("quantity")),
                name="subscription_allotted_within_quantity",
                violation_error_message=ALLOTTED_ABOVE_REQUESTED_ERROR,
            ),
            models.CheckConstraint(
                condition=models.Q(settlement_rail=SettlementRail.BANK_TRANSFER, settlement_asset__isnull=True)
                | models.Q(settlement_rail=SettlementRail.STABLECOIN, settlement_asset__isnull=False),
                name="subscription_rail_matches_settlement_asset",
                violation_error_message=RAIL_ASSET_PAIRING_ERROR,
            ),
        ]

    def __str__(self):
        return f"{self.quantity} shares of {self.offering.token.symbol} ({self.get_status_display()})"

    @property
    def allotment_quantity(self) -> int:
        return self.quantity if self.allotted_quantity is None else self.allotted_quantity

    @property
    def amount_outstanding(self):
        return self.amount_due - (self.amount_received or 0)

    @property
    def refunded_total(self) -> Decimal:
        if self.refunded_at is None:
            return ZERO
        return self.refund_amount or ZERO

    @property
    def money_held(self) -> Decimal:
        return (self.amount_received or ZERO) - self.refunded_total

    @property
    def money_backing_shares(self) -> Decimal:
        if self.status != SubscriptionStatus.ALLOTTED:
            return ZERO
        return (Decimal(self.allotment_quantity) * self.price_per_share).quantize(CENTS)

    @property
    def amount_refundable(self) -> Decimal:
        return max(self.money_held - self.money_backing_shares, ZERO)

    @property
    def has_money_in(self) -> bool:
        return self.amount_received is not None and self.money_held > ZERO

    def _require_status(self, allowed, to_status):
        if self.status not in allowed:
            raise InvalidSubscriptionTransitionException(
                from_status=self.get_status_display(), to_status=to_status.label
            )

    def submit(self, submitted_by=None):
        self._require_status([SubscriptionStatus.DRAFT], SubscriptionStatus.SUBMITTED)
        self.status = SubscriptionStatus.SUBMITTED
        self.submitted_by = submitted_by
        self.save(update_fields=["status", "submitted_by", "updated_at"])

    def accept(self):
        self._require_status([SubscriptionStatus.SUBMITTED], SubscriptionStatus.ACCEPTED)
        self.status = SubscriptionStatus.ACCEPTED
        self.save(update_fields=["status", "updated_at"])

    def mark_awaiting_payment(self, rail, settlement_asset, settlement_amount, reference, due_at):
        self._require_status([SubscriptionStatus.ACCEPTED], SubscriptionStatus.AWAITING_PAYMENT)
        self.status = SubscriptionStatus.AWAITING_PAYMENT
        self.settlement_rail = rail
        self.settlement_asset = settlement_asset
        self.settlement_amount = settlement_amount
        self.reference = reference
        self.payment_due_at = due_at
        self.payment_instruction_issued_at = timezone.now()
        self.save(update_fields=self._instruction_fields())

    @staticmethod
    def _instruction_fields():
        return [
            "status",
            "settlement_rail",
            "settlement_asset",
            "settlement_amount",
            "reference",
            "payment_due_at",
            "payment_instruction_issued_at",
            "updated_at",
        ]

    def record_payment(self, status, allotted_quantity, refund_amount, confirmed_by, **fields):
        self._require_status([SubscriptionStatus.AWAITING_PAYMENT, SubscriptionStatus.PAID], status)
        self.status = status
        self.allotted_quantity = allotted_quantity
        self.refund_amount = refund_amount
        self.payment_confirmed_by = confirmed_by
        self.payment_confirmed_at = timezone.now()
        for name, value in fields.items():
            setattr(self, name, value)
        self.save(update_fields=self._payment_fields() + list(fields))

    @staticmethod
    def _payment_fields():
        return [
            "status",
            "allotted_quantity",
            "refund_amount",
            "payment_confirmed_by",
            "payment_confirmed_at",
            "updated_at",
        ]

    def mark_allotted(self):
        self._require_status([SubscriptionStatus.PAID], SubscriptionStatus.ALLOTTED)
        self.status = SubscriptionStatus.ALLOTTED
        self.save(update_fields=["status", "updated_at"])

    def mark_refunded(self, amount, reference, notes):
        self._require_status(REFUNDABLE_SUBSCRIPTION_STATUSES, SubscriptionStatus.REFUNDED)
        self.refund_amount = self.refunded_total + amount
        self.refund_reference = reference
        self.refunded_at = timezone.now()
        self.payment_notes = notes
        if self.status != SubscriptionStatus.ALLOTTED:
            self.status = SubscriptionStatus.REFUNDED
        self.save(update_fields=REFUND_FIELDS)

    def _require_no_money_in(self):
        if self.has_money_in:
            raise SubscriptionRefusedException(
                MONEY_ALREADY_IN.format(amount=self.money_held, reference=self.reference or self.uuid)
            )

    def reject(self, notes):
        self._require_status(CLOSEABLE_SUBSCRIPTION_STATUSES, SubscriptionStatus.REJECTED)
        self._require_no_money_in()
        self.status = SubscriptionStatus.REJECTED
        self.payment_notes = notes
        self.save(update_fields=["status", "payment_notes", "updated_at"])

    def withdraw(self, notes):
        self._require_status(CLOSEABLE_SUBSCRIPTION_STATUSES, SubscriptionStatus.WITHDRAWN)
        self._require_no_money_in()
        self.status = SubscriptionStatus.WITHDRAWN
        self.payment_notes = notes
        self.save(update_fields=["status", "payment_notes", "updated_at"])
