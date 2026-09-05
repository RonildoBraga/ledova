from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.querysets import SwapOrderQuerySet

from .choices import SwapOrderStatus

if TYPE_CHECKING:
    from blockchain.models import BlockchainTransaction


class SwapOrder(BaseModel):
    objects = SwapOrderQuerySet.as_manager()

    sell_order = models.ForeignKey(
        "tokens.TransferOrder",
        on_delete=models.CASCADE,
        related_name="swap_as_sell",
    )
    buy_order = models.ForeignKey(
        "tokens.TransferOrder",
        on_delete=models.CASCADE,
        related_name="swap_as_buy",
    )

    share_token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.CASCADE,
        related_name="swap_orders",
    )
    payment_asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        related_name="swap_orders",
    )

    seller_address = models.CharField(max_length=42)
    buyer_address = models.CharField(max_length=42)

    share_amount = models.PositiveBigIntegerField(help_text="Number of shares to transfer (no decimals)")
    payment_amount = models.PositiveBigIntegerField(
        help_text="Payment amount in stablecoin smallest units (e.g., cents for 2 decimals)"
    )

    nonce = models.PositiveBigIntegerField(help_text="Unique nonce for replay protection")
    order_hash = models.CharField(
        max_length=66,
        unique=True,
        help_text="EIP-712 typed data hash",
    )

    seller_signature = models.TextField(
        blank=True,
        help_text="EIP-712 signature from seller",
    )
    buyer_signature = models.TextField(
        blank=True,
        help_text="EIP-712 signature from buyer",
    )

    status = models.CharField(
        max_length=20,
        choices=SwapOrderStatus.choices,
        default=SwapOrderStatus.CREATED,
    )
    expires_at = models.DateTimeField()

    tx_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Transaction hash when executed on-chain (legacy field)",
    )
    transaction = models.ForeignKey(
        "blockchain.BlockchainTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="swap_orders",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "Swap Order"
        verbose_name_plural = "Swap Orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["seller_address"]),
            models.Index(fields=["buyer_address"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["share_token", "status"]),
        ]

    def __str__(self):
        return f"Swap {self.share_amount} {self.share_token.symbol} @ {self.payment_amount}"

    @property
    def is_expired(self):
        if self.status == SwapOrderStatus.EXPIRED:
            return True
        return (
            self.status
            in [
                SwapOrderStatus.CREATED,
                SwapOrderStatus.SELLER_SIGNED,
                SwapOrderStatus.BUYER_SIGNED,
            ]
            and timezone.now() > self.expires_at
        )

    @property
    def is_ready(self):
        return (
            self.seller_signature
            and self.buyer_signature
            and self.status == SwapOrderStatus.READY
            and not self.is_expired
        )

    @property
    def seller_has_signed(self):
        return bool(self.seller_signature)

    @property
    def buyer_has_signed(self):
        return bool(self.buyer_signature)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            default_hours = getattr(settings, "SWAP_ORDER_EXPIRY_HOURS", 24)
            self.expires_at = timezone.now() + timedelta(hours=default_hours)
        super().save(*args, **kwargs)

    def add_seller_signature(self, signature: str):
        self.seller_signature = signature
        if self.buyer_signature:
            self.status = SwapOrderStatus.READY
        else:
            self.status = SwapOrderStatus.SELLER_SIGNED
        self.save(update_fields=["seller_signature", "status", "updated_at"])

    def add_buyer_signature(self, signature: str):
        self.buyer_signature = signature
        if self.seller_signature:
            self.status = SwapOrderStatus.READY
        else:
            self.status = SwapOrderStatus.BUYER_SIGNED
        self.save(update_fields=["buyer_signature", "status", "updated_at"])

    def mark_executing(self, tx_hash: str, transaction: "BlockchainTransaction" = None):
        self.tx_hash = tx_hash
        self.status = SwapOrderStatus.EXECUTING
        update_fields = ["tx_hash", "status", "updated_at"]
        if transaction:
            self.transaction = transaction
            update_fields.append("transaction")
        self.save(update_fields=update_fields)

    def mark_completed(self):
        self.status = SwapOrderStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

        from .choices import TransferOrderStatus

        for order in [self.sell_order, self.buy_order]:
            order.tx_hash = self.tx_hash

            if order.filled_quantity >= order.quantity:
                order.status = TransferOrderStatus.COMPLETED
                order.completed_at = self.completed_at
                update_fields = ["status", "completed_at", "tx_hash", "updated_at"]
            else:

                order.status = TransferOrderStatus.OPEN
                update_fields = ["status", "tx_hash", "updated_at"]

            order.save(update_fields=update_fields)

    def mark_failed(self, error_message: str):
        self.status = SwapOrderStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

        from .choices import TransferOrderStatus

        for order in [self.sell_order, self.buy_order]:
            if order.status in [TransferOrderStatus.FAILED, TransferOrderStatus.COMPLETED]:
                continue

            order.filled_quantity = max(0, (order.filled_quantity or 0) - self.share_amount)

            if order.filled_quantity > 0:
                order.status = TransferOrderStatus.PARTIALLY_FILLED
            else:
                order.status = TransferOrderStatus.OPEN

            order.error_message = error_message
            order.save(update_fields=["filled_quantity", "status", "error_message", "updated_at"])
