from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.querysets import CapitalIncreaseRequestQuerySet

from .choices import CapitalIncreaseStatus


class CapitalIncreaseRequest(BaseModel):

    objects = CapitalIncreaseRequestQuerySet.as_manager()

    token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.CASCADE,
        related_name="capital_increase_requests",
    )

    additional_shares = models.PositiveIntegerField(
        help_text="Number of additional shares to authorize and mint",
    )
    new_authorized_total = models.PositiveIntegerField(
        help_text="New total authorized shares after increase",
    )
    purpose = models.TextField(
        help_text="Purpose or justification for this capital increase",
    )
    board_resolution_reference = models.CharField(
        max_length=255,
        help_text="Reference to board resolution authorizing this increase",
    )
    shareholder_approval_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reference to shareholder approval (if required)",
    )

    status = models.CharField(
        max_length=20,
        choices=CapitalIncreaseStatus.choices,
        default=CapitalIncreaseStatus.DRAFT,
    )

    dilution_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Percentage dilution this increase would cause to existing holders",
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_capital_increases",
        help_text="User who submitted the request",
    )
    submitted_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the request was submitted",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_capital_increases",
        help_text="Staff member who reviewed the request",
    )
    reviewed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the request was reviewed",
    )
    review_notes = models.TextField(
        blank=True,
        help_text="Notes from the reviewer",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if rejected)",
    )

    executed_issuance = models.OneToOneField(
        "tokens.ShareIssuance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capital_increase",
        help_text="The executed ShareIssuance record for the minted shares",
    )
    executed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the capital increase was executed on-chain",
    )

    class Meta:
        verbose_name = "Capital Increase Request"
        verbose_name_plural = "Capital Increase Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "status"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.token.symbol}: +{self.additional_shares} shares ({self.get_status_display()})"

    @property
    def is_draft(self) -> bool:
        return self.status == CapitalIncreaseStatus.DRAFT

    @property
    def is_submitted(self) -> bool:
        return self.status == CapitalIncreaseStatus.SUBMITTED

    @property
    def is_pending_review(self) -> bool:
        return self.status in [
            CapitalIncreaseStatus.SUBMITTED,
            CapitalIncreaseStatus.UNDER_REVIEW,
        ]

    @property
    def is_approved(self) -> bool:
        return self.status == CapitalIncreaseStatus.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status == CapitalIncreaseStatus.REJECTED

    @property
    def is_executed(self) -> bool:
        return self.status == CapitalIncreaseStatus.EXECUTED

    @property
    def can_be_edited(self) -> bool:
        return self.status == CapitalIncreaseStatus.DRAFT

    @property
    def can_be_submitted(self) -> bool:
        return self.status == CapitalIncreaseStatus.DRAFT

    @property
    def can_be_approved(self) -> bool:
        return self.status in [
            CapitalIncreaseStatus.SUBMITTED,
            CapitalIncreaseStatus.UNDER_REVIEW,
        ]

    @property
    def can_be_executed(self) -> bool:
        return self.status == CapitalIncreaseStatus.APPROVED

    @property
    def can_retry_execution(self) -> bool:
        return self.status == CapitalIncreaseStatus.FAILED

    def calculate_dilution(self) -> float:
        from tokens.models import IssuanceStatus, ShareIssuance

        completed_issuances = ShareIssuance.objects.filter(
            token=self.token,
            status=IssuanceStatus.COMPLETED,
        ).values_list("amount", flat=True)

        current_supply = sum(int(amount) for amount in completed_issuances if amount)

        if current_supply == 0:
            return 0.0

        new_supply = current_supply + self.additional_shares
        dilution = (self.additional_shares / new_supply) * 100
        return round(dilution, 2)

    def submit(self, user) -> None:
        if not self.can_be_submitted:
            raise ValueError(f"Cannot submit request with status '{self.get_status_display()}'")

        self.dilution_percentage = self.calculate_dilution()

        self.status = CapitalIncreaseStatus.SUBMITTED
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "submitted_by",
                "submitted_at",
                "dilution_percentage",
                "updated_at",
            ]
        )

    def start_review(self, reviewer) -> None:
        if self.status != CapitalIncreaseStatus.SUBMITTED:
            raise ValueError("Can only start review on submitted requests")

        self.status = CapitalIncreaseStatus.UNDER_REVIEW
        self.reviewed_by = reviewer
        self.save(update_fields=["status", "reviewed_by", "updated_at"])

    def approve(self, reviewer, notes: str = "") -> None:
        if not self.can_be_approved:
            raise ValueError(f"Cannot approve request with status '{self.get_status_display()}'")

        self.status = CapitalIncreaseStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_notes",
                "updated_at",
            ]
        )

    def reject(self, reviewer, reason: str) -> None:
        if not self.can_be_approved:
            raise ValueError(f"Cannot reject request with status '{self.get_status_display()}'")

        self.status = CapitalIncreaseStatus.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "updated_at",
            ]
        )

    def mark_executing(self) -> None:
        if not self.can_be_executed and not self.can_retry_execution:
            raise ValueError(f"Cannot execute request with status '{self.get_status_display()}'")

        self.status = CapitalIncreaseStatus.EXECUTING
        self.save(update_fields=["status", "updated_at"])

    def mark_executed(self, issuance) -> None:
        self.status = CapitalIncreaseStatus.EXECUTED
        self.executed_issuance = issuance
        self.executed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "executed_issuance",
                "executed_at",
                "updated_at",
            ]
        )

    def mark_failed(self, error: str) -> None:
        self.status = CapitalIncreaseStatus.FAILED
        self.review_notes = f"Execution failed: {error}"
        self.save(update_fields=["status", "review_notes", "updated_at"])
