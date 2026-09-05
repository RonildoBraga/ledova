from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.querysets import ShareTokenQuerySet

from .choices import ShareTokenStatus, ShareTokenType

if TYPE_CHECKING:
    from blockchain.models import BlockchainTransaction


class ShareToken(BaseModel):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    token_type = models.CharField(
        max_length=20,
        choices=ShareTokenType.choices,
        default=ShareTokenType.ORDINARY,
    )

    total_supply = models.CharField(max_length=78)
    decimals = models.PositiveSmallIntegerField(default=0)
    is_transferable = models.BooleanField(default=True)
    is_divisible = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=ShareTokenStatus.choices,
        default=ShareTokenStatus.DRAFT,
    )
    contract_address = models.CharField(max_length=42, blank=True, null=True, unique=True)
    deployment_tx_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Transaction hash of deployment (legacy field)",
    )
    deployment_transaction = models.ForeignKey(
        "blockchain.BlockchainTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deployed_share_tokens",
    )
    deployed_at = models.DateTimeField(blank=True, null=True)

    objects = ShareTokenQuerySet.as_manager()

    class Meta:
        verbose_name = "Share Token"
        verbose_name_plural = "Share Tokens"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "symbol"],
                name="unique_company_symbol",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.symbol})"

    @property
    def is_deployed(self) -> bool:
        return self.status == ShareTokenStatus.DEPLOYED and self.contract_address is not None

    def mark_deploying(self, tx_hash: str = None, transaction: BlockchainTransaction = None) -> None:
        self.status = ShareTokenStatus.DEPLOYING
        update_fields = ["status", "updated_at"]
        if tx_hash:
            self.deployment_tx_hash = tx_hash
            update_fields.append("deployment_tx_hash")
        if transaction:
            self.deployment_transaction = transaction
            update_fields.append("deployment_transaction")
        self.save(update_fields=update_fields)

    def bind_deployment_transaction(self, tx_hash: str, transaction: BlockchainTransaction) -> bool:
        now = timezone.now()
        bound = (
            type(self)
            .objects.filter(pk=self.pk)
            .filter(models.Q(deployment_tx_hash__isnull=True) | models.Q(deployment_tx_hash=""))
            .update(
                status=ShareTokenStatus.DEPLOYING,
                deployment_tx_hash=tx_hash,
                deployment_transaction=transaction,
                updated_at=now,
            )
        )
        if bound:
            self.status = ShareTokenStatus.DEPLOYING
            self.deployment_tx_hash = tx_hash
            self.deployment_transaction = transaction
            self.updated_at = now
        else:
            self.refresh_from_db(fields=["status", "deployment_tx_hash", "deployment_transaction", "updated_at"])
        return bool(bound)

    def mark_draft(self) -> None:
        self.status = ShareTokenStatus.DRAFT
        self.save(update_fields=["status", "updated_at"])

    def mark_draft_unless_sent(self) -> bool:
        now = timezone.now()
        drafted = (
            type(self)
            .objects.filter(pk=self.pk)
            .filter(models.Q(deployment_tx_hash__isnull=True) | models.Q(deployment_tx_hash=""))
            .update(status=ShareTokenStatus.DRAFT, updated_at=now)
        )
        if drafted:
            self.status = ShareTokenStatus.DRAFT
            self.updated_at = now
        else:
            self.refresh_from_db(fields=["status", "deployment_tx_hash", "deployment_transaction", "updated_at"])
        return bool(drafted)

    def discard_deployment_transaction(self) -> None:
        self.deployment_tx_hash = None
        self.deployment_transaction = None
        self.save(update_fields=["deployment_tx_hash", "deployment_transaction", "updated_at"])

    def mark_deployed(self, contract_address: str) -> None:
        self.status = ShareTokenStatus.DEPLOYED
        self.contract_address = contract_address
        self.deployed_at = timezone.now()
        self.save(update_fields=["status", "contract_address", "deployed_at", "updated_at"])

    def mark_paused(self) -> None:
        self.status = ShareTokenStatus.PAUSED
        self.save(update_fields=["status", "updated_at"])

    def mark_unpaused(self) -> None:
        if self.contract_address:
            self.status = ShareTokenStatus.DEPLOYED
        else:
            self.status = ShareTokenStatus.DRAFT
        self.save(update_fields=["status", "updated_at"])
