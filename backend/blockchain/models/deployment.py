from django.db import models

from blockchain.querysets.deployment import ContractDeploymentQuerySet
from shared.models.base import BaseModel


class ContractDeployment(BaseModel):
    objects = ContractDeploymentQuerySet.as_manager()

    name = models.CharField(max_length=100)
    address = models.CharField(max_length=42, unique=True)
    version = models.CharField(max_length=20, default="1.0.0")
    deployer_address = models.CharField(max_length=42)
    deployment_tx = models.OneToOneField(
        "blockchain.BlockchainTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deployed_contract",
    )
    block_number = models.PositiveIntegerField()
    abi_hash = models.CharField(max_length=66, null=True, blank=True)
    constructor_args = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    chain_id = models.PositiveIntegerField(default=1337)

    class Meta:
        verbose_name = "Contract Deployment"
        verbose_name_plural = "Contract Deployments"
        ordering = ["-created_at"]
        unique_together = [["name", "chain_id", "version"]]

    def __str__(self) -> str:
        return f"{self.name} @ {self.address[:10]}... (v{self.version})"
