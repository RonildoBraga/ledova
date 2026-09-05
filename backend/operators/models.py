import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from web3 import Web3

from assets.models import AssetType
from shared.constants import BLOCKCHAIN_BASE, BLOCKCHAIN_ETHEREUM

SINGLETON_PK = 1
STABLECOIN_ONLY = {"asset_type": AssetType.STABLECOIN.value}
MAX_PAYMENT_REFERENCE_PREFIX = 10
NOT_A_STABLECOIN = "{symbol} is not a stablecoin asset."


def settlement_errors(assets, field: str, chain: str) -> dict:
    from operators.settlement import NOT_DEPLOYED, deployment_on_chain

    for asset in assets:
        if asset.asset_type != AssetType.STABLECOIN.value:
            return {field: NOT_A_STABLECOIN.format(symbol=asset.symbol)}
        if deployment_on_chain(asset, chain) is None:
            return {field: NOT_DEPLOYED.format(symbol=asset.symbol, chain=chain)}
    return {}


class DeploymentMode(models.TextChoices):
    SINGLE_ISSUER = "single_issuer", "Single issuer (one company on its own instance)"
    REGISTRY = "registry", "Registry (many companies on one instance)"


class ReceivingChain(models.TextChoices):
    ETHEREUM = BLOCKCHAIN_ETHEREUM, "Ethereum"
    BASE = BLOCKCHAIN_BASE, "Base"


def _digits(value: str) -> str:
    return re.sub(r"[\s-]", "", value or "")


class Operator(models.Model):

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_PK, editable=False)

    name = models.CharField(max_length=120)
    legal_name = models.CharField(max_length=255, blank=True)
    abn = models.CharField(max_length=14, blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    deployment_mode = models.CharField(max_length=20, choices=DeploymentMode.choices, default=DeploymentMode.REGISTRY)

    bank_account_name = models.CharField(max_length=255, blank=True)
    bank_bsb = models.CharField(max_length=7, blank=True)
    bank_account_number = models.CharField(max_length=20, blank=True)
    payment_reference_prefix = models.CharField(
        max_length=16, blank=True, help_text="Letters and digits; subscription references start with it."
    )
    receiving_wallet_address = models.CharField(max_length=42, blank=True)
    receiving_wallet_chain = models.CharField(
        max_length=20, choices=ReceivingChain.choices, default=ReceivingChain.BASE
    )
    issued_stablecoin = models.ForeignKey(
        "assets.Asset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        limit_choices_to=STABLECOIN_ONLY,
    )
    supported_settlement_assets = models.ManyToManyField(
        "assets.Asset", blank=True, related_name="+", limit_choices_to=STABLECOIN_ONLY
    )

    investor_kyc_required = models.BooleanField(default=True)
    issuer_kyc_required = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Operator"
        verbose_name_plural = "Operator"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=SINGLETON_PK), name="operators_operator_single_row"),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def get(cls) -> "Operator":
        operator, _ = cls.objects.get_or_create(pk=SINGLETON_PK, defaults={"name": settings.OPERATOR_NAME})
        return operator

    def save(self, *args, **kwargs):
        self.id = SINGLETON_PK
        if self._state.adding and Operator.objects.filter(pk=SINGLETON_PK).exists():
            raise ValidationError("Only one operator row can exist; edit the existing one.")
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        self.abn = _digits(self.abn)
        if self.abn and not re.fullmatch(r"\d{11}", self.abn):
            errors["abn"] = "ABN must be exactly 11 digits."
        self.bank_bsb = _digits(self.bank_bsb)
        if self.bank_bsb and not re.fullmatch(r"\d{6}", self.bank_bsb):
            errors["bank_bsb"] = "BSB must be exactly 6 digits."
        self.payment_reference_prefix = (self.payment_reference_prefix or "").strip().upper()
        if self.payment_reference_prefix and not re.fullmatch(
            rf"[A-Z0-9]{{2,{MAX_PAYMENT_REFERENCE_PREFIX}}}", self.payment_reference_prefix
        ):
            errors["payment_reference_prefix"] = f"Use 2 to {MAX_PAYMENT_REFERENCE_PREFIX} letters or digits."
        self.receiving_wallet_address = (self.receiving_wallet_address or "").strip()
        if self.receiving_wallet_address:
            if Web3.is_address(self.receiving_wallet_address):
                self.receiving_wallet_address = Web3.to_checksum_address(self.receiving_wallet_address)
            else:
                errors["receiving_wallet_address"] = "Enter a valid EVM address."
        if self.issued_stablecoin_id:
            errors.update(settlement_errors([self.issued_stablecoin], "issued_stablecoin", self.receiving_wallet_chain))
        if errors:
            raise ValidationError(errors)
