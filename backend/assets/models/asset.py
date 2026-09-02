from enum import Enum
from typing import TYPE_CHECKING, Optional

from django.db import models

if TYPE_CHECKING:
    from assets.models.asset_chain_deployment import AssetChainDeployment

from assets.querysets.asset import AssetQuerySet
from shared.models import BaseModel


class AssetType(str, Enum):

    NATIVE_CRYPTO = "native_crypto"  # BTC, ETH, SOL (chain-native coins)
    ERC20_TOKEN = "erc20_token"  # LINK, UNI, AAVE (ERC-20 tokens on Ethereum)
    STABLECOIN = "stablecoin"  # USDC, USDT, DAI
    TOKENIZED_SECURITY = "tokenized_security"  # AAPL.t, VAS.t
    TOKENIZED_RWA = "tokenized_rwa"  # US Treasuries, bonds
    SYNTHETIC = "synthetic"  # Synthetic tracking tokens

    @classmethod
    def choices(cls):
        return [(item.value, item.name.replace("_", " ").title()) for item in cls]


class Asset(BaseModel):

    symbol = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=255)

    asset_type = models.CharField(max_length=32, choices=AssetType.choices())

    decimals = models.IntegerField(default=18)

    current_price = models.DecimalField(max_digits=40, decimal_places=18, null=True, blank=True)
    price_currency = models.CharField(max_length=16, default="USD")

    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)

    objects = AssetQuerySet.as_manager()

    class Meta:
        verbose_name = "Asset"
        verbose_name_plural = "Assets"
        indexes = [
            models.Index(fields=["symbol"], name="idx_asset_symbol"),
            models.Index(fields=["asset_type"], name="idx_asset_type"),
        ]
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.symbol} - {self.name}"

    def __repr__(self):
        return f"<Asset: {self.symbol} ({self.asset_type})>"

    @property
    def chain(self):
        dep = self.chain_deployments.first()
        return dep.chain if dep else None

    @property
    def contract_address(self):
        dep = self.chain_deployments.first()
        return dep.contract_address if dep else None

    @property
    def is_native_token(self):
        return not self.chain_deployments.filter(contract_address__isnull=False).exclude(contract_address="").exists()

    @property
    def is_erc20_token(self):
        return self.chain_deployments.filter(contract_address__isnull=False).exclude(contract_address="").exists()

    @property
    def display_price(self):
        if self.current_price is None:
            return "N/A"
        return f"{self.price_currency} {self.current_price:,.2f}"

    def get_deployment_for_chain(self, chain: str) -> Optional["AssetChainDeployment"]:
        return self.chain_deployments.filter(chain=chain, is_active=True).first()

    @classmethod
    def get_by_chain_and_contract(cls, chain: str, contract_address: str) -> Optional["Asset"]:
        from assets.models.asset_chain_deployment import AssetChainDeployment

        deployment = (
            AssetChainDeployment.objects.select_related("asset")
            .filter(chain=chain, contract_address__iexact=contract_address, is_active=True)
            .first()
        )
        return deployment.asset if deployment else None
