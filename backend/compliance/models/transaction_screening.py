from django.db import models

from compliance.constants import (
    SCREENING_RESULT_CHOICES,
    SCREENING_STATUS_CHOICES,
    SCREENING_STATUS_PENDING,
)
from integrations.kyc.constants import PROVIDER_KYCAID
from shared.models.base import BaseModel


class TransactionScreening(BaseModel):
    """Blockchain-analytics result for one transaction's destination address (sanctions, mixers, darknet...)."""

    transaction = models.OneToOneField(
        "wallets.Transaction",
        on_delete=models.CASCADE,
        related_name="screening",
        help_text="Crypto transaction that was screened",
    )
    user_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.CASCADE,
        related_name="transaction_screenings",
    )
    provider = models.CharField(
        max_length=20,
        default=PROVIDER_KYCAID,
        help_text="KYT provider used for this screening",
    )
    provider_transaction_id = models.CharField(
        max_length=100,
        db_index=True,
        blank=True,
        null=True,
        help_text="Provider transaction/request ID",
    )
    status = models.CharField(
        max_length=20,
        choices=SCREENING_STATUS_CHOICES,
        default=SCREENING_STATUS_PENDING,
    )
    result = models.CharField(
        max_length=20,
        choices=SCREENING_RESULT_CHOICES,
        null=True,
        blank=True,
        help_text="Final screening result: approved, review, or rejected",
    )
    risk_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Risk score from 0 (low) to 1.0+ (high)",
    )
    risk_level = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Risk level: LOW, MEDIUM, or HIGH",
    )
    risk_signals = models.JSONField(
        default=list,
        help_text="List of risk signals detected (sanctions, mixer, darknet, etc.)",
    )
    to_address = models.CharField(
        max_length=100,
        help_text="Destination wallet address that was screened",
    )
    from_address = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Source wallet address (if applicable)",
    )
    raw_response = models.JSONField(
        default=dict,
        help_text="Complete response from provider API for audit purposes",
    )
    submitted_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the screening was submitted",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the screening result was received",
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if screening failed",
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["to_address"]),
            models.Index(fields=["risk_score"]),
            models.Index(fields=["user_account", "-created_at"]),
        ]

    def __str__(self):
        return f"Screening {self.provider_transaction_id} - {self.status}"
