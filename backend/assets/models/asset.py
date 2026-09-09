from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from django.db import models

from assets.choices import PriceSource

if TYPE_CHECKING:
    from assets.models.asset_chain_deployment import AssetChainDeployment

from assets.querysets.asset import AssetQuerySet
from shared.models import BaseModel


class AssetType(str, Enum):

    NATIVE_CRYPTO = "native_crypto"
    ERC20_TOKEN = "erc20_token"
    STABLECOIN = "stablecoin"
    TOKENIZED_SECURITY = "tokenized_security"
    TOKENIZED_RWA = "tokenized_rwa"
    SYNTHETIC = "synthetic"

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
    price_source = models.CharField(max_length=12, choices=PriceSource.choices, default=PriceSource.MARKET, null=True)

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
    def valuation_price(self):
        if self.price_source in PriceSource.values and self.price_currency == "USD" and self.current_price is not None:
            price = Decimal(self.current_price)
            return price if price.is_finite() and price > 0 else None
        return None

    @property
    def value_source(self):
        return self.price_source if self.valuation_price is not None else "unpriced"

    def get_deployment_for_chain(self, chain: str) -> Optional["AssetChainDeployment"]:
        return self.chain_deployments.filter(chain=chain, is_active=True).first()

    @classmethod
    def get_by_chain_and_contract(cls, chain: str, contract_address: str) -> Optional["Asset"]:
        return cls.objects.for_chain_and_contract(chain, contract_address)
