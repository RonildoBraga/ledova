from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.querysets import MintRequestQuerySet


class MintRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    EXECUTED = "executed", "Executed"
    FAILED = "failed", "Failed"
    REJECTED = "rejected", "Rejected"


class MintRequest(BaseModel):

    objects = MintRequestQuerySet.as_manager()

    stablecoin = models.ForeignKey(
        "tokens.Stablecoin",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mint_requests",
        help_text="The stablecoin being minted (if applicable)",
    )

    yield_token = models.ForeignKey(
        "tokens.YieldToken",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mint_requests",
        help_text="The yield token being minted (if applicable)",
    )

    recipient_address = models.CharField(
        max_length=42,
        help_text="Wallet address to receive the minted tokens",
    )

    recipient_name = models.CharField(
        max_length=200,
        help_text="Name of the recipient (for audit purposes)",
    )

    amount = models.BigIntegerField(
        help_text=(
            "Amount to mint in raw units "
            "(e.g., 10000 = $100.00 for 2-decimal stablecoin, 1000000 = 1.000000 for 6-decimal yield token)"
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=MintRequestStatus.choices,
        default=MintRequestStatus.PENDING,
    )

    deposit_reference = models.CharField(
        max_length=100,
        help_text="Synthetic scenario reference or test case ID",
    )

    deposit_date = models.DateField(
        help_text="Date assigned to the synthetic scenario",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mint_requests_created",
        help_text="Staff member who created this request",
    )

    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mint_requests_executed",
        help_text="Staff member who executed this request",
    )

    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the mint was executed",
    )

    transaction = models.ForeignKey(
        "blockchain.BlockchainTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mint_requests",
    )

    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this mint request",
    )

    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if rejected)",
    )

    error_message = models.TextField(
        blank=True,
        help_text="Error message if mint failed",
    )

    class Meta:
        verbose_name = "Mint Request"
        verbose_name_plural = "Mint Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["deposit_reference"]),
            models.Index(fields=["recipient_address"]),
        ]

    def __str__(self):
        token = self.token
        symbol = token.symbol if token else "?"
        return f"Mint {self.amount_display} {symbol} to {self.recipient_name} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        has_stablecoin = self.stablecoin_id is not None
        has_yield_token = self.yield_token_id is not None
        if has_stablecoin == has_yield_token:
            raise ValidationError("Exactly one of stablecoin or yield_token must be set.")

    @property
    def token(self):
        return self.stablecoin or self.yield_token

    @property
    def amount_display(self) -> str:
        token = self.token
        decimals = token.decimals if token else 2
        return f"{self.amount / (10 ** decimals):,.{decimals}f}"

    @property
    def can_be_executed(self) -> bool:
        return self.status in [MintRequestStatus.PENDING, MintRequestStatus.APPROVED]

    @property
    def can_be_rejected(self) -> bool:
        return self.status in [MintRequestStatus.PENDING, MintRequestStatus.APPROVED]

    @property
    def can_retry(self) -> bool:
        return self.status == MintRequestStatus.FAILED

    def mark_executed(self, user, transaction):
        self.status = MintRequestStatus.EXECUTED
        self.executed_by = user
        self.executed_at = timezone.now()
        self.transaction = transaction
        self.save(update_fields=["status", "executed_by", "executed_at", "transaction", "updated_at"])

    def mark_failed(self, error_message: str):
        self.status = MintRequestStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_rejected(self, user, reason: str):
        self.status = MintRequestStatus.REJECTED
        self.executed_by = user
        self.executed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "executed_by", "executed_at", "rejection_reason", "updated_at"])
