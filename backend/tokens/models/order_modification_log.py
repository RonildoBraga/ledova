from django.db import models

from shared.models import BaseModel


class OrderModificationLog(BaseModel):

    order = models.ForeignKey(
        "tokens.TransferOrder",
        on_delete=models.CASCADE,
        related_name="modification_logs",
        help_text="The order that was modified.",
    )

    field_name = models.CharField(
        max_length=50,
        help_text="Name of the field that was modified (e.g., 'quantity', 'price_per_share').",
    )
    old_value = models.CharField(
        max_length=100,
        help_text="The value before modification.",
    )
    new_value = models.CharField(
        max_length=100,
        help_text="The value after modification.",
    )

    modification_message = models.TextField(
        help_text="The message that was signed to authorize this modification.",
    )
    signature = models.TextField(
        help_text="The cryptographic signature authorizing this modification.",
    )
    signer_address = models.CharField(
        max_length=42,
        help_text="The wallet address that signed the modification.",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request that made this modification.",
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string from the request.",
    )

    class Meta:
        verbose_name = "Order Modification Log"
        verbose_name_plural = "Order Modification Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "created_at"]),
            models.Index(fields=["signer_address"]),
            models.Index(fields=["field_name"]),
        ]

    def __str__(self):
        return f"{self.order_id}: {self.field_name} {self.old_value} → {self.new_value}"
