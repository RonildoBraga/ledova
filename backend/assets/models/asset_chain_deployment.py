from django.db import models

from shared.models import BaseModel


class AssetChainDeployment(BaseModel):

    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.CASCADE,
        related_name="chain_deployments",
    )
    chain = models.CharField(
        max_length=32,
        help_text="Blockchain (ethereum, base, bitcoin, etc.)",
    )
    contract_address = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        help_text="Contract address on this chain (null for native assets like ETH, BTC)",
    )
    decimals = models.IntegerField(
        default=18,
        help_text="Token decimals on this chain",
    )
    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        db_table = "asset_chain_deployments"
        verbose_name = "Asset Chain Deployment"
        verbose_name_plural = "Asset Chain Deployments"
        ordering = ["asset", "chain"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "chain"],
                name="unique_asset_chain",
            ),
            models.UniqueConstraint(
                fields=["chain", "contract_address"],
                name="unique_chain_contract",
                condition=models.Q(contract_address__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["chain", "contract_address"], name="idx_deploy_chain_contract"),
        ]

    def __str__(self):
        addr = self.contract_address[:10] + "..." if self.contract_address else "native"
        return f"{self.asset.symbol} on {self.chain} ({addr})"

    def __repr__(self):
        return f"<AssetChainDeployment: {self.asset.symbol} on {self.chain}>"
