from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel

if TYPE_CHECKING:
    from wallets.models import Wallet


class SignatureRequestType(models.TextChoices):
    TOKEN_DEPLOY = "token_deploy", "Deploy Token"
    SHARE_ISSUE = "share_issue", "Issue Shares"
    SHARE_TRANSFER = "share_transfer", "Transfer Shares"
    TOKEN_PAUSE = "token_pause", "Pause Token"
    TOKEN_UNPAUSE = "token_unpause", "Unpause Token"
    WHITELIST_ADD = "whitelist_add", "Add to Whitelist"
    WHITELIST_REMOVE = "whitelist_remove", "Remove from Whitelist"
    OTHER = "other", "Other"


class SignatureRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending Signature"
    SIGNED = "signed", "Signed"
    SUBMITTED = "submitted", "Submitted to Blockchain"
    CONFIRMED = "confirmed", "Confirmed"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class SignatureRequest(BaseModel):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="signature_requests",
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signature_requests",
    )

    request_type = models.CharField(
        max_length=30,
        choices=SignatureRequestType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=SignatureRequestStatus.choices,
        default=SignatureRequestStatus.PENDING,
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    transaction_data = models.JSONField()
    message_to_sign = models.TextField(blank=True)

    signature = models.TextField(blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    tx_hash = models.CharField(max_length=66, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    expires_at = models.DateTimeField()
    error_message = models.TextField(blank=True)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_signature_requests",
    )
    initiated_from = models.CharField(
        max_length=20,
        choices=[("admin", "Admin Panel"), ("portal", "Company Portal")],
        default="portal",
    )

    related_model = models.CharField(max_length=100, blank=True)
    related_uuid = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = "Signature Request"
        verbose_name_plural = "Signature Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["request_type"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

    @property
    def is_pending(self):
        return self.status == SignatureRequestStatus.PENDING

    @property
    def is_expired(self):
        if self.status == SignatureRequestStatus.EXPIRED:
            return True
        if self.status == SignatureRequestStatus.PENDING and timezone.now() > self.expires_at:
            return True
        return False

    @property
    def can_sign(self):
        return self.status == SignatureRequestStatus.PENDING and timezone.now() < self.expires_at

    def sign(self, signature: str, wallet: "Wallet" = None):
        if not self.can_sign:
            raise ValueError("Cannot sign: request is not pending or has expired")

        self.signature = signature
        self.signed_at = timezone.now()
        self.status = SignatureRequestStatus.SIGNED
        if wallet:
            self.wallet = wallet

        self.save(update_fields=["signature", "signed_at", "status", "wallet", "updated_at"])

    def mark_submitted(self, tx_hash: str):
        self.tx_hash = tx_hash
        self.status = SignatureRequestStatus.SUBMITTED
        self.save(update_fields=["tx_hash", "status", "updated_at"])

    def mark_confirmed(self):
        self.status = SignatureRequestStatus.CONFIRMED
        self.confirmed_at = timezone.now()
        self.save(update_fields=["status", "confirmed_at", "updated_at"])

    def mark_failed(self, error_message: str):
        self.status = SignatureRequestStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_expired(self):
        self.status = SignatureRequestStatus.EXPIRED
        self.save(update_fields=["status", "updated_at"])

    def cancel(self):
        if self.status not in [SignatureRequestStatus.PENDING]:
            raise ValueError("Only pending requests can be cancelled")
        self.status = SignatureRequestStatus.CANCELLED
        self.save(update_fields=["status", "updated_at"])
