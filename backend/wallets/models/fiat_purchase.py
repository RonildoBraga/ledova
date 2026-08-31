from django.conf import settings
from django.db import models

from shared.models import BaseModel
from wallets.models.wallet import Wallet


class FiatTransaction(BaseModel):

    PROVIDER_CHOICES = [
        ("TRANSAK", "Transak"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("CANCELLED", "Cancelled"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("CARD", "Credit/Debit Card"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("APPLE_PAY", "Apple Pay"),
        ("GOOGLE_PAY", "Google Pay"),
    ]

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="TRANSAK")
    external_id = models.CharField(max_length=255, unique=True, db_index=True)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="fiat_transactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fiat_transactions")
    fiat_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fiat_currency = models.CharField(max_length=3, default="USD")
    crypto_amount = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    crypto_currency = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, null=True, blank=True)
    transaction_hash = models.CharField(max_length=255, null=True, blank=True)
    provider_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    network_fee = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    provider_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "fiat_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["wallet", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Fiat Transaction"
        verbose_name_plural = "Fiat Transactions"

    def __str__(self):
        return f"{self.fiat_amount} {self.fiat_currency} → {self.crypto_amount or '?'} {self.crypto_currency}"
