from django.db import models

from assets.models import Asset
from shared.models import BaseModel
from wallets.constants import TRANSACTION_STATUS_CHOICES, TRANSACTION_STATUS_PENDING
from wallets.models.wallet import Blockchain, Wallet
from wallets.querysets.transaction import TransactionQuerySet


class Transaction(BaseModel):
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
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES, default=TRANSACTION_STATUS_PENDING)
    transaction_fee_estimated = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    transaction_fee = models.DecimalField(max_digits=30, decimal_places=18, null=True, blank=True)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")

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
