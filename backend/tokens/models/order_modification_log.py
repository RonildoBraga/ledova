from django.db import models

from shared.models import BaseModel


class OrderModificationLog(BaseModel):
    """Immutable audit trail: one row per changed field per signed order modification."""

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

    @classmethod
    def log_modification(
        cls,
        order,
        field_name: str,
        old_value,
        new_value,
        message: str,
        signature: str,
        signer_address: str,
        ip_address: str = None,
        user_agent: str = None,
    ):
        return cls.objects.create(
            order=order,
            field_name=field_name,
            old_value=str(old_value),
            new_value=str(new_value),
            modification_message=message,
            signature=signature,
            signer_address=signer_address,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else "",
        )

    @classmethod
    def log_multiple_modifications(
        cls,
        order,
        changes: list[tuple[str, any, any]],
        message: str,
        signature: str,
        signer_address: str,
        ip_address: str = None,
        user_agent: str = None,
    ):
        logs = []
        for field_name, old_value, new_value in changes:
            log = cls.log_modification(
                order=order,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                message=message,
                signature=signature,
                signer_address=signer_address,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            logs.append(log)
        return logs
