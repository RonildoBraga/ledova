from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone
from web3 import Web3

from shared.models import BaseModel
from tokens.querysets import ShareIssuanceQuerySet

from .choices import IssuanceStatus, IssuanceType

if TYPE_CHECKING:
    from blockchain.models import BlockchainTransaction


class ShareIssuance(BaseModel):

    objects = ShareIssuanceQuerySet.as_manager()

    token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.CASCADE,
        related_name="issuances",
    )

    recipient_address = models.CharField(
        max_length=42,
        help_text="Ethereum address receiving the shares (0x...)",
    )
    recipient_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional name/label for the recipient",
    )

    amount = models.CharField(
        max_length=78,
        help_text="Number of shares issued (as string for large numbers)",
    )
    issuance_type = models.CharField(
        max_length=20,
        choices=IssuanceType.choices,
        default=IssuanceType.ADDITIONAL,
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason or notes for the issuance",
    )

    status = models.CharField(
        max_length=20,
        choices=IssuanceStatus.choices,
        default=IssuanceStatus.PENDING,
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error details if issuance failed",
    )

    tx_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Transaction hash of the issuance (legacy field)",
    )
    block_number = models.PositiveBigIntegerField(
        blank=True,
        null=True,
        help_text="Block number where transaction was mined (legacy field)",
    )
    gas_used = models.PositiveBigIntegerField(
        blank=True,
        null=True,
        help_text="Gas used by the transaction (legacy field)",
    )
    transaction = models.ForeignKey(
        "blockchain.BlockchainTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="share_issuances",
    )

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_issuances",
        help_text="User who initiated the issuance",
    )
    processed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the blockchain transaction was submitted",
    )
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the blockchain transaction was confirmed",
    )

    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        help_text="Unique key to prevent duplicate issuances",
    )

    class Meta:
        verbose_name = "Share Issuance"
        verbose_name_plural = "Share Issuances"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "status"]),
            models.Index(fields=["recipient_address"]),
            models.Index(fields=["tx_hash"]),
        ]

    def __str__(self):
        return f"{self.token.symbol}: {self.amount} → {self.recipient_address[:10]}..."

    @property
    def is_completed(self) -> bool:
        return self.status == IssuanceStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == IssuanceStatus.FAILED

    def mark_processing(self, tx_hash: str = None) -> None:
        self.status = IssuanceStatus.PROCESSING
        self.processed_at = timezone.now()
        update_fields = ["status", "processed_at", "updated_at"]

        if tx_hash:
            self.tx_hash = tx_hash
            update_fields.append("tx_hash")

        self.save(update_fields=update_fields)

    def mark_completed(
        self,
        tx_hash: str = None,
        block_number: int = None,
        gas_used: int = None,
        transaction: BlockchainTransaction = None,
    ) -> None:
        self.status = IssuanceStatus.COMPLETED
        self.completed_at = timezone.now()
        update_fields = ["status", "completed_at", "updated_at"]

        if tx_hash:
            self.tx_hash = tx_hash
            update_fields.append("tx_hash")
        if block_number:
            self.block_number = block_number
            update_fields.append("block_number")
        if gas_used:
            self.gas_used = gas_used
            update_fields.append("gas_used")
        if transaction:
            self.transaction = transaction
            update_fields.append("transaction")

        self.save(update_fields=update_fields)

    def mark_failed(self, error_message: str) -> None:
        """Failed after or before sending; a recorded tx_hash is kept so a retry can resume on it."""
        self.status = IssuanceStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_reverted(self, error_message: str) -> None:
        """The recorded mint was mined and reverted: nothing was minted, so the hash is forgotten for a fresh mint."""
        self.status = IssuanceStatus.FAILED
        self.error_message = error_message
        self.tx_hash = None
        self.save(update_fields=["status", "error_message", "tx_hash", "updated_at"])

    def save(self, *args, **kwargs):
        if self.recipient_address:
            self.recipient_address = Web3.to_checksum_address(self.recipient_address)
        super().save(*args, **kwargs)
