from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel

from .choices import RequestStatus
from .share_issuance import ShareIssuance


class ReviewableRequest(BaseModel):
    """Staff review workflow (submit, review, approve or reject, execute) shared by the two share-request models.

    Each concrete model adds its own fields plus `share_delta`, the number of shares the request would mint.
    """

    share_delta: int

    status = models.CharField(
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.DRAFT,
    )
    dilution_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Percentage dilution this request would cause to existing holders",
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_%(class)ss",
        help_text="User who submitted the request",
    )
    submitted_at = models.DateTimeField(blank=True, null=True, help_text="When the request was submitted")

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_%(class)ss",
        help_text="Staff member who reviewed the request",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True, help_text="When the request was reviewed")
    review_notes = models.TextField(blank=True, help_text="Notes from the reviewer")
    rejection_reason = models.TextField(blank=True, help_text="Reason for rejection (if rejected)")

    executed_issuance = models.OneToOneField(
        "tokens.ShareIssuance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s",
        help_text="The executed ShareIssuance record for the minted shares",
    )
    executed_at = models.DateTimeField(blank=True, null=True, help_text="When the request was executed on-chain")

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "status"]),
            models.Index(fields=["status"]),
        ]

    @property
    def can_be_approved(self) -> bool:
        return self.status in (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW)

    @property
    def can_be_executed(self) -> bool:
        """Approved requests execute; failed ones may be retried."""
        return self.status in (RequestStatus.APPROVED, RequestStatus.FAILED)

    def calculate_dilution(self) -> float:
        current_supply = ShareIssuance.objects.completed_supply(self.token)
        if current_supply == 0:
            return 0.0
        return round(self.share_delta / (current_supply + self.share_delta) * 100, 2)

    def start_review(self, reviewer) -> None:
        if self.status != RequestStatus.SUBMITTED:
            raise ValueError("Can only start review on submitted requests")
        self.status = RequestStatus.UNDER_REVIEW
        self.reviewed_by = reviewer
        self.save(update_fields=["status", "reviewed_by", "updated_at"])

    def approve(self, reviewer, notes: str = "") -> None:
        self._review("approve", RequestStatus.APPROVED, reviewer, review_notes=notes)

    def reject(self, reviewer, reason: str) -> None:
        self._review("reject", RequestStatus.REJECTED, reviewer, rejection_reason=reason)

    def _review(self, verb, status, reviewer, **fields) -> None:
        if not self.can_be_approved:
            raise ValueError(f"Cannot {verb} request with status '{self.get_status_display()}'")
        self.status = status
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        for name, value in fields.items():
            setattr(self, name, value)
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", *fields, "updated_at"])

    def mark_executing(self) -> None:
        if not self.can_be_executed:
            raise ValueError(f"Cannot execute request with status '{self.get_status_display()}'")
        self.status = RequestStatus.EXECUTING
        self.save(update_fields=["status", "updated_at"])

    def mark_executed(self, issuance) -> None:
        self.status = RequestStatus.EXECUTED
        self.executed_issuance = issuance
        self.executed_at = timezone.now()
        self.save(update_fields=["status", "executed_issuance", "executed_at", "updated_at"])

    def mark_failed(self, error: str) -> None:
        self.status = RequestStatus.FAILED
        self.review_notes = f"Execution failed: {error}"
        self.save(update_fields=["status", "review_notes", "updated_at"])
