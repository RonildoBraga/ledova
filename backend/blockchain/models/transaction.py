from django.db import models
from django.utils import timezone

from blockchain.querysets.transaction import BlockchainTransactionQuerySet
from shared.models.base import BaseModel


class TransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUBMITTED = "submitted", "Submitted"
    CONFIRMED = "confirmed", "Confirmed"
    FAILED = "failed", "Failed"
    REVERTED = "reverted", "Reverted"


class TransactionType(models.TextChoices):
    WHITELIST_ADD = "whitelist_add", "Add to Whitelist"
    WHITELIST_REMOVE = "whitelist_remove", "Remove from Whitelist"
    WHITELIST_UPDATE = "whitelist_update", "Update Investor Type"
    TOKEN_DEPLOY = "token_deploy", "Deploy Token"
    TOKEN_MINT = "token_mint", "Mint Tokens"
    TOKEN_TRANSFER = "token_transfer", "Transfer Tokens"
    TOKEN_BURN = "token_burn", "Burn Tokens"
    STABLECOIN_MINT = "stablecoin_mint", "Mint Stablecoin"
    STABLECOIN_BURN = "stablecoin_burn", "Burn Stablecoin"
    YIELD_TOKEN_MINT = "yield_token_mint", "Mint Yield Token"
    YIELD_TOKEN_NAV_UPDATE = "yield_token_nav_update", "Update Yield Token NAV"
    ATOMIC_SWAP = "atomic_swap", "Atomic Swap"
    SHARE_TOKEN_DEPLOY = "share_token_deploy", "Deploy Share Token"
    CONTRACT_DEPLOY = "contract_deploy", "Deploy Contract"
    OTHER = "other", "Other"


class BlockchainTransaction(BaseModel):
    tx_hash = models.CharField(max_length=66, unique=True, null=True, blank=True)
    tx_type = models.CharField(
        max_length=30,
        choices=TransactionType.choices,
        default=TransactionType.OTHER,
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
    )
    from_address = models.CharField(max_length=42)
    to_address = models.CharField(max_length=42, null=True, blank=True)
    value = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    gas_limit = models.PositiveIntegerField(null=True, blank=True)
    gas_price = models.DecimalField(max_digits=36, decimal_places=18, null=True, blank=True)
    gas_used = models.PositiveIntegerField(null=True, blank=True)
    nonce = models.PositiveIntegerField(null=True, blank=True)
    block_number = models.PositiveIntegerField(null=True, blank=True)
    block_hash = models.CharField(max_length=66, null=True, blank=True)
    function_name = models.CharField(max_length=100, null=True, blank=True)
    function_args = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    related_model = models.CharField(max_length=100, null=True, blank=True)
    related_uuid = models.UUIDField(null=True, blank=True)

    objects = BlockchainTransactionQuerySet.as_manager()

    class Meta:
        verbose_name = "Blockchain Transaction"
        verbose_name_plural = "Blockchain Transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tx_hash"]),
            models.Index(fields=["status"]),
            models.Index(fields=["tx_type"]),
            models.Index(fields=["from_address"]),
            models.Index(fields=["to_address"]),
            models.Index(fields=["block_number"]),
        ]

    def __str__(self) -> str:
        if self.tx_hash:
            return f"{self.tx_type} - {self.tx_hash[:10]}..."
        return f"{self.tx_type} - {self.status}"

    @property
    def is_pending(self) -> bool:
        return self.status in [TransactionStatus.PENDING, TransactionStatus.SUBMITTED]

    @property
    def is_successful(self) -> bool:
        return self.status == TransactionStatus.CONFIRMED

    @property
    def is_failed(self) -> bool:
        return self.status in [TransactionStatus.FAILED, TransactionStatus.REVERTED]

    @property
    def explorer_url(self) -> str | None:
        if not self.tx_hash:
            return None
        return None

    def mark_submitted(self, tx_hash: str, nonce: int = None) -> None:
        self.tx_hash = tx_hash
        self.status = TransactionStatus.SUBMITTED
        self.submitted_at = timezone.now()
        if nonce is not None:
            self.nonce = nonce
        self.save(update_fields=["tx_hash", "status", "submitted_at", "nonce", "updated_at"])

    def mark_confirmed(
        self,
        block_number: int,
        block_hash: str,
        gas_used: int,
    ) -> None:
        self.status = TransactionStatus.CONFIRMED
        self.block_number = block_number
        self.block_hash = block_hash
        self.gas_used = gas_used
        self.confirmed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "block_number",
                "block_hash",
                "gas_used",
                "confirmed_at",
                "updated_at",
            ]
        )

    def mark_failed(self, error_message: str) -> None:
        self.status = TransactionStatus.FAILED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_reverted(self, error_message: str = "") -> None:
        self.status = TransactionStatus.REVERTED
        self.error_message = error_message
        self.save(update_fields=["status", "error_message", "updated_at"])
