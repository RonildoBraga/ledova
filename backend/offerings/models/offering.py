from django.conf import settings
from django.db import models
from django.utils import timezone

from offerings.exceptions import InvalidOfferingTransitionException
from offerings.querysets.offering import OfferingQuerySet
from operators.models import STABLECOIN_ONLY
from shared.constants import CURRENCY_AUD, CURRENCY_CHOICES
from shared.models import BaseModel

BOUNDS_ORDERED_ERROR = "Minimum, target and cap must be at least one share and ordered minimum <= target <= cap."
WINDOW_ORDERED_ERROR = "An offering must close after it opens."


class OfferingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted for Review"
    UNDER_REVIEW = "under_review", "Under Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CLOSED = "closed", "Closed"
    WITHDRAWN = "withdrawn", "Withdrawn"


LIVE_OFFERING_STATUSES = [OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW, OfferingStatus.APPROVED]


class OfferingExemption(models.TextChoices):
    MINIMUM_AMOUNT = "s708_8_minimum_amount", "Minimum amount of AUD 500,000 (s708(8)(a))"
    NET_ASSETS = "s708_8_net_assets", "Net assets certified by a qualified accountant (s708(8)(c))"
    GROSS_INCOME = "s708_8_gross_income", "Gross income certified by a qualified accountant (s708(8)(c))"
    PROFESSIONAL = "s708_11_professional", "Professional investor (s708(11))"
    WHOLESALE_CLIENT = "s761g_wholesale_client", "Wholesale client (s761G)"


class Offering(BaseModel):

    objects = OfferingQuerySet.as_manager()

    token = models.ForeignKey("tokens.ShareToken", on_delete=models.CASCADE, related_name="offerings")

    status = models.CharField(max_length=20, choices=OfferingStatus.choices, default=OfferingStatus.DRAFT)
    exemption = models.CharField(max_length=30, choices=OfferingExemption.choices)

    price_per_share = models.DecimalField(max_digits=18, decimal_places=2)
    price_currency = models.CharField(max_length=16, choices=CURRENCY_CHOICES, default=CURRENCY_AUD)

    settlement_assets = models.ManyToManyField(
        "assets.Asset", blank=True, related_name="offerings", limit_choices_to=STABLECOIN_ONLY
    )
    accepts_bank_transfer = models.BooleanField(default=True)

    minimum_shares = models.PositiveIntegerField()
    target_shares = models.PositiveIntegerField()
    cap_shares = models.PositiveIntegerField()
    maximum_shares = models.PositiveIntegerField(null=True, blank=True)

    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField(null=True, blank=True)

    summary = models.TextField(blank=True)
    use_of_proceeds = models.TextField(blank=True)

    documents = models.ManyToManyField("companies.CompanyDocument", blank=True, related_name="offerings")

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_offerings",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_offerings",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Offering"
        verbose_name_plural = "Offerings"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "opens_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["token"],
                condition=models.Q(status__in=LIVE_OFFERING_STATUSES),
                name="offering_one_live_per_token",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_shares__gte=1)
                & models.Q(target_shares__gte=models.F("minimum_shares"))
                & models.Q(cap_shares__gte=models.F("target_shares")),
                name="offering_bounds_ordered",
                violation_error_message=BOUNDS_ORDERED_ERROR,
            ),
            models.CheckConstraint(
                condition=models.Q(closes_at__isnull=True) | models.Q(closes_at__gt=models.F("opens_at")),
                name="offering_window_ordered",
                violation_error_message=WINDOW_ORDERED_ERROR,
            ),
        ]

    def __str__(self):
        return f"{self.token.symbol} offering ({self.get_status_display()})"

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_OFFERING_STATUSES

    @property
    def is_open(self) -> bool:
        if self.status != OfferingStatus.APPROVED or self.opens_at > timezone.now():
            return False
        return self.closes_at is None or self.closes_at > timezone.now()

    @property
    def can_be_edited(self) -> bool:
        return self.status == OfferingStatus.DRAFT

    def _require_status(self, allowed, to_status):
        if self.status not in allowed:
            raise InvalidOfferingTransitionException(from_status=self.get_status_display(), to_status=to_status.label)

    def submit(self, submitted_by=None):
        self._require_status([OfferingStatus.DRAFT], OfferingStatus.SUBMITTED)
        self.status = OfferingStatus.SUBMITTED
        self.submitted_at = timezone.now()
        self.submitted_by = submitted_by
        self.save(update_fields=["status", "submitted_at", "submitted_by", "updated_at"])

    def start_review(self, reviewed_by=None):
        self._require_status([OfferingStatus.SUBMITTED], OfferingStatus.UNDER_REVIEW)
        self.status = OfferingStatus.UNDER_REVIEW
        self.reviewed_by = reviewed_by
        self.save(update_fields=["status", "reviewed_by", "updated_at"])

    def approve(self, reviewed_by=None, notes=""):
        self._require_status([OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW], OfferingStatus.APPROVED)
        self.status = OfferingStatus.APPROVED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])

    def reject(self, reviewed_by=None, reason=""):
        self._require_status([OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW], OfferingStatus.REJECTED)
        self.status = OfferingStatus.REJECTED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    def close(self, reason=""):
        self._require_status([OfferingStatus.APPROVED], OfferingStatus.CLOSED)
        self.status = OfferingStatus.CLOSED
        self.closed_at = timezone.now()
        self.close_reason = reason
        self.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])

    def withdraw(self, reason=""):
        pending = [OfferingStatus.DRAFT, OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW]
        self._require_status(pending, OfferingStatus.WITHDRAWN)
        self.status = OfferingStatus.WITHDRAWN
        self.closed_at = timezone.now()
        self.close_reason = reason
        self.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
