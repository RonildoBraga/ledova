from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.querysets import ShareIssuanceRequestQuerySet

from .choices import IssuanceRequestStatus, IssuanceType


class ShareIssuanceRequest(BaseModel):

    objects = ShareIssuanceRequestQuerySet.as_manager()

    token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.CASCADE,
        related_name="issuance_requests",
    )

    recipient_address = models.CharField(
        max_length=42,
        help_text="Ethereum address of the recipient",
    )
    recipient_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the recipient (optional)",
    )
    amount = models.PositiveIntegerField(
        help_text="Number of shares to issue",
    )
    issuance_type = models.CharField(
        max_length=20,
        choices=IssuanceType.choices,
        default=IssuanceType.ADDITIONAL,
        help_text="Type of issuance",
    )
    reason = models.TextField(
        help_text="Purpose or justification for this issuance",
    )

    dilution_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Percentage dilution this issuance would cause to existing holders",
    )

    status = models.CharField(
        max_length=20,
        choices=IssuanceRequestStatus.choices,
        default=IssuanceRequestStatus.PENDING_APPROVAL,
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_issuance_requests",
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
        related_name="reviewed_issuance_requests",
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
        related_name="issuance_request",
        help_text="The executed ShareIssuance record for the minted shares",
    )
    executed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the issuance was executed on-chain",
    )

    class Meta:
        verbose_name = "Share Issuance Request"
        verbose_name_plural = "Share Issuance Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "status"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        addr = self.recipient_address[:10]
        return f"{self.token.symbol}: {self.amount} shares to {addr}... ({self.get_status_display()})"

    @property
    def can_be_approved(self) -> bool:
        return self.status in [
            IssuanceRequestStatus.PENDING_APPROVAL,
            IssuanceRequestStatus.UNDER_REVIEW,
        ]

    @property
    def can_be_executed(self) -> bool:
        return self.status == IssuanceRequestStatus.APPROVED

    @property
    def can_retry_execution(self) -> bool:
        return self.status == IssuanceRequestStatus.FAILED

    def calculate_dilution(self) -> float:
        from tokens.models import IssuanceStatus, ShareIssuance

        completed_issuances = ShareIssuance.objects.filter(
            token=self.token,
            status=IssuanceStatus.COMPLETED,
        ).values_list("amount", flat=True)

        current_supply = sum(int(amount) for amount in completed_issuances if amount)

        if current_supply == 0:
            return 0.0

        new_supply = current_supply + self.amount
        dilution = (self.amount / new_supply) * 100
        return round(dilution, 2)

    def start_review(self, reviewer) -> None:
        if self.status != IssuanceRequestStatus.PENDING_APPROVAL:
            raise ValueError("Can only start review on pending requests")

        self.status = IssuanceRequestStatus.UNDER_REVIEW
        self.reviewed_by = reviewer
        self.save(update_fields=["status", "reviewed_by", "updated_at"])

    def approve(self, reviewer, notes: str = "") -> None:
        if not self.can_be_approved:
            raise ValueError(f"Cannot approve request with status '{self.get_status_display()}'")

        self.status = IssuanceRequestStatus.APPROVED
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

        self.status = IssuanceRequestStatus.REJECTED
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

        self.status = IssuanceRequestStatus.EXECUTING
        self.save(update_fields=["status", "updated_at"])

    def mark_executed(self, issuance) -> None:
        self.status = IssuanceRequestStatus.EXECUTED
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
        self.status = IssuanceRequestStatus.FAILED
        self.review_notes = f"Execution failed: {error}"
        self.save(update_fields=["status", "review_notes", "updated_at"])
