from django.db import models

from assets.models import Asset
from shared.models import BaseModel
from wallets.constants import TRANSACTION_STATUS_CHOICES, TRANSACTION_STATUS_PENDING
from wallets.models.owner_column import DerivesAccountFromWallet
from wallets.models.wallet import Blockchain, Wallet
from wallets.querysets.transaction import TransactionQuerySet


class Transaction(DerivesAccountFromWallet, BaseModel):
    tx_hash = models.CharField(max_length=255, db_index=True)
    chain = models.CharField(
        max_length=20,
        choices=Blockchain.choices(),
        db_index=True,
    )
    from_address = models.CharField(max_length=255, db_index=True)
    to_address = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="transactions")
    amount = models.DecimalField(max_digits=30, decimal_places=18)
    market_value = models.DecimalField(
        max_digits=30,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="USD value at transaction time (amount × asset price at block_timestamp)",
    )
    block_timestamp = models.DateTimeField(db_index=True, null=True, blank=True)
    block_number = models.BigIntegerField(null=True, blank=True)
    block_hash = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Hash of the block this landed in, so a reorganisation that replaced it can be seen",
    )
    nonce = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Sender's nonce for this broadcast, which is what ties a replacement to what it replaced",
    )
    replaced_by_tx_hash = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="The hash that landed instead of this one, for a speed-up or a cancellation",
    )
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES, default=TRANSACTION_STATUS_PENDING)
    transaction_fee_estimated = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    transaction_fee = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    deducted_amount = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        null=True,
        blank=True,
        help_text=(
            "What the optimistic deduction actually took from the asset's holding, after the floor at zero. "
            "Carries the fee as well when the asset is the chain's native coin. Null for rows written before "
            "the deduction was recorded."
        ),
    )
    deducted_fee = models.DecimalField(
        max_digits=30,
        decimal_places=18,
        null=True,
        blank=True,
        help_text=(
            "What the optimistic deduction actually took from the native holding, after the floor at zero. "
            "Null when the asset is itself native, and for rows written before the deduction was recorded."
        ),
    )
    deducted_amount_sync_version = models.UUIDField(null=True, blank=True, editable=False)
    deducted_fee_sync_version = models.UUIDField(null=True, blank=True, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")

    user_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.CASCADE,
        related_name="+",
        help_text=(
            "Owner, derived from wallet.user_account and held directly so a " "row-level security policy can read it"
        ),
    )

    objects = TransactionQuerySet.as_manager()

    class Meta:
        db_table = "transactions"
        ordering = ["-block_timestamp"]
        unique_together = [["tx_hash", "wallet"]]
        indexes = [
            models.Index(fields=["tx_hash"]),
            models.Index(fields=["from_address"]),
            models.Index(fields=["to_address"]),
            models.Index(fields=["wallet", "-block_timestamp"]),
            models.Index(fields=["chain", "-block_timestamp"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"

    def __str__(self):
        return f"{self.tx_hash[:16]}... ({self.asset.symbol})"
