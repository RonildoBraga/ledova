from enum import Enum

from django.db import models

from shared.models import BaseModel
from users.models import UserAccount
from wallets.constants import (
    WALLET_VERIFICATION_STATUS_CHOICES,
    WALLET_VERIFICATION_STATUS_PENDING,
    WALLET_VERIFICATION_STATUS_VERIFIED,
)
from wallets.querysets.wallet import WalletQuerySet


class WalletType(str, Enum):
    HARDWARE = "hardware"
    SOFTWARE = "software"

    @classmethod
    def choices(cls):
        return [(item.value, item.name.replace("_", " ").title()) for item in cls]


class Blockchain(str, Enum):
    ETHEREUM = "ethereum"
    BITCOIN = "bitcoin"
    POLYGON = "polygon"
    SOLANA = "solana"
    AVALANCHE = "avalanche"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    BASE = "base"

    @classmethod
    def choices(cls):
        return [(item.value, item.value.upper()) for item in cls]


class Wallet(BaseModel):
    user_account = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="wallets")
    name = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(
        max_length=255, db_index=True
    )  # Not unique - same wallet can be tracked by multiple users
    chain = models.CharField(
        max_length=20,
        choices=Blockchain.choices(),
        db_index=True,
    )
    wallet_type = models.CharField(
        max_length=16,
        choices=WalletType.choices(),
        default=WalletType.HARDWARE.value,
    )
    verification_status = models.CharField(
        max_length=20, choices=WALLET_VERIFICATION_STATUS_CHOICES, default=WALLET_VERIFICATION_STATUS_PENDING
    )
    verification_challenge = models.TextField(null=True, blank=True)
    verification_signature = models.TextField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    derivation_path = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Full BIP44 derivation path to this address (e.g., m/44'/60'/0'/0/0)",
    )
    master_fingerprint = models.CharField(
        max_length=8,
        null=True,
        blank=True,
        help_text="Hardware wallet identifier (8-char hex)",
    )
    address_index = models.IntegerField(
        null=True,
        blank=True,
        help_text="Index of this address in the derivation sequence (0, 1, 2, ...)",
    )
    parent_public_key = models.CharField(
        max_length=66,
        null=True,
        blank=True,
        help_text="Public key at external chain level (33-byte compressed, hex)",
    )
    parent_chain_code = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Chain code at external chain level (32-byte, hex)",
    )
    parent_derivation_path = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Derivation path of the parent key (e.g., m/44'/60'/0'/0)",
    )

    objects = WalletQuerySet.as_manager()

    class Meta:
        db_table = "wallets"
        ordering = ["-created_at"]
        unique_together = [["user_account", "address"]]
        indexes = [
            models.Index(fields=["user_account", "verification_status"]),
            models.Index(fields=["chain"]),
        ]
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self):
        chain_display = self.chain.upper() if self.chain else "?"
        if self.name:
            return f"{self.name} - {self.address[:10]}... ({chain_display})"
        return f"{self.address[:10]}... ({chain_display})"

    @property
    def is_verified(self):
        return self.verification_status == WALLET_VERIFICATION_STATUS_VERIFIED
