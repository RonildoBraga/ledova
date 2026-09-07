from django.db import models
from django.utils import timezone

from tokens.exceptions import InvalidTokenStateException
from tokens.querysets import CapitalIncreaseRequestQuerySet

from .choices import IN_FLIGHT_STATUSES, RequestStatus
from .owner_column import DerivesCompanyFromToken
from .review_request import ReviewableRequest


class CapitalIncreaseRequest(DerivesCompanyFromToken, ReviewableRequest):

    objects = CapitalIncreaseRequestQuerySet.as_manager()

    token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.PROTECT,
        related_name="capital_increase_requests",
    )

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=("Owner, derived from token.company and held directly so a " "row-level security policy can read it"),
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

    class Meta(ReviewableRequest.Meta):
        verbose_name = "Capital Increase Request"
        verbose_name_plural = "Capital Increase Requests"
        constraints = [
            models.UniqueConstraint(
                fields=["token"],
                condition=models.Q(status__in=IN_FLIGHT_STATUSES),
                name="one_capital_increase_in_flight_per_token",
            )
        ]

    def __str__(self):
        return f"{self.token.symbol}: +{self.additional_shares} shares ({self.get_status_display()})"

    @property
    def share_delta(self) -> int:
        return self.additional_shares

    @property
    def can_be_edited(self) -> bool:
        return self.status == RequestStatus.DRAFT

    can_be_submitted = can_be_edited

    def submit(self, user, dilution_percentage) -> None:
        if not self.can_be_submitted:
            raise InvalidTokenStateException(f"Cannot submit request with status '{self.get_status_display()}'.")

        self.dilution_percentage = dilution_percentage
        self.status = RequestStatus.SUBMITTED
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_by", "submitted_at", "dilution_percentage", "updated_at"])
