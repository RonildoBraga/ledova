from django.db import models

from tokens.querysets import ShareIssuanceRequestQuerySet

from .choices import IssuanceType, RequestStatus
from .review_request import ReviewableRequest


class ShareIssuanceRequest(ReviewableRequest):
    """Created already submitted by ShareTokenService.create_issuance_request, so there is no draft stage."""

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
    status = models.CharField(
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.SUBMITTED,
    )

    class Meta(ReviewableRequest.Meta):
        verbose_name = "Share Issuance Request"
        verbose_name_plural = "Share Issuance Requests"

    def __str__(self):
        addr = self.recipient_address[:10]
        return f"{self.token.symbol}: {self.amount} shares to {addr}... ({self.get_status_display()})"

    @property
    def share_delta(self) -> int:
        return self.amount
