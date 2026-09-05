from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.querysets import TransferOrderQuerySet

from .choices import TransferOrderStatus, TransferOrderType


class TransferOrder(BaseModel):
    objects = TransferOrderQuerySet.as_manager()

    token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.CASCADE,
        related_name="transfer_orders",
    )
    payment_token = models.ForeignKey(
        "tokens.Stablecoin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfer_orders",
    )
    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="transfer_orders",
        help_text="Verified tenant wallet that owns this order.",
    )
    owner_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.PROTECT,
        related_name="transfer_orders",
        help_text="Immutable tenant snapshot for this order.",
    )

    order_type = models.CharField(
        max_length=10,
        choices=TransferOrderType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=TransferOrderStatus.choices,
        default=TransferOrderStatus.OPEN,
    )

    wallet_address = models.CharField(max_length=42)
    quantity = models.PositiveBigIntegerField()
    price_per_share = models.DecimalField(max_digits=18, decimal_places=2)

    min_quantity = models.PositiveBigIntegerField(
        default=0,
        help_text="Minimum quantity per fill. 0 means exact match only (min_quantity = remaining).",
    )
    filled_quantity = models.PositiveBigIntegerField(
        default=0,
        help_text="Total quantity already filled across all partial fills.",
    )

    original_quantity = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Original quantity at order creation (set on first modification).",
    )
    original_price = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original price at order creation (set on first modification).",
    )
    modification_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this order has been modified.",
    )
    last_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent modification.",
    )
    current_signature = models.TextField(
        blank=True,
        help_text="Signature from the most recent modification (or creation if unmodified).",
    )

    matched_order = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_by",
    )

    exchange_order_id = models.CharField(max_length=66, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    tx_hash = models.CharField(max_length=66, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "Transfer Order"
        verbose_name_plural = "Transfer Orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "status"]),
            models.Index(fields=["wallet_address"]),
            models.Index(fields=["order_type", "status"]),
        ]

    def __str__(self):
        return f"{self.get_order_type_display()} {self.quantity} {self.token.symbol} @ ${self.price_per_share}"

    @property
    def total_value(self):
        return self.quantity * self.price_per_share

    @property
    def remaining_quantity(self):
        return self.quantity - self.filled_quantity

    @property
    def remaining_value(self):
        return self.remaining_quantity * self.price_per_share

    @property
    def effective_min_quantity(self):
        """min_quantity of 0 means exact-match mode: the whole remaining quantity."""
        if self.min_quantity == 0:
            return self.remaining_quantity
        return min(self.min_quantity, self.remaining_quantity)

    @property
    def can_cancel(self):
        return self.status in [TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED]

    @property
    def can_be_modified(self):
        return (
            self.status in [TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED]
            and not self.has_pending_swap
        )

    @property
    def has_pending_swap(self):
        from .choices import SwapOrderStatus

        pending_statuses = [
            SwapOrderStatus.CREATED,
            SwapOrderStatus.SELLER_SIGNED,
            SwapOrderStatus.BUYER_SIGNED,
            SwapOrderStatus.READY,
            SwapOrderStatus.EXECUTING,
        ]
        return (
            self.swap_as_sell.filter(status__in=pending_statuses).exists()
            or self.swap_as_buy.filter(status__in=pending_statuses).exists()
        )

    def partial_match_with(self, other_order: "TransferOrder", match_quantity: int):
        """Full fills become MATCHED and partial fills PARTIALLY_FILLED on both orders."""
        self.filled_quantity = (self.filled_quantity or 0) + match_quantity
        self.matched_order = other_order

        if self.filled_quantity >= self.quantity:
            self.status = TransferOrderStatus.MATCHED
        else:
            self.status = TransferOrderStatus.PARTIALLY_FILLED

        self.save(update_fields=["filled_quantity", "matched_order", "status", "updated_at"])

        other_order.filled_quantity = (other_order.filled_quantity or 0) + match_quantity
        other_order.matched_order = self

        if other_order.filled_quantity >= other_order.quantity:
            other_order.status = TransferOrderStatus.MATCHED
        else:
            other_order.status = TransferOrderStatus.PARTIALLY_FILLED

        other_order.save(update_fields=["filled_quantity", "matched_order", "status", "updated_at"])

    def mark_executing(self, tx_hash: str):
        self.tx_hash = tx_hash
        self.status = TransferOrderStatus.EXECUTING
        self.save(update_fields=["tx_hash", "status", "updated_at"])

    def mark_completed(self):
        self.status = TransferOrderStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

        if self.matched_order and self.matched_order.status != TransferOrderStatus.COMPLETED:
            self.matched_order.status = TransferOrderStatus.COMPLETED
            self.matched_order.completed_at = timezone.now()
            self.matched_order.tx_hash = self.tx_hash
            self.matched_order.save(update_fields=["status", "completed_at", "tx_hash", "updated_at"])

    def mark_failed(self, error_message: str):
        self.status = TransferOrderStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

        if self.matched_order and self.matched_order.status not in [
            TransferOrderStatus.FAILED,
            TransferOrderStatus.COMPLETED,
        ]:
            self.matched_order.status = TransferOrderStatus.FAILED
            self.matched_order.error_message = error_message
            self.matched_order.save(update_fields=["status", "error_message", "updated_at"])

    def cancel(self):
        if not self.can_cancel:
            raise ValueError("Order cannot be cancelled")
        self.status = TransferOrderStatus.CANCELLED
        self.save(update_fields=["status", "updated_at"])

    def record_original_values(self):
        """Snapshot the pre-modification values the first time an order is modified."""
        if self.original_quantity is None:
            self.original_quantity = self.quantity
        if self.original_price is None:
            self.original_price = self.price_per_share
