from django.conf import settings
from django.db import models

from shared.models import BaseModel
from tokens.models.choices import IDENTITY_SOURCE_CHOICES, IDENTITY_UNKNOWN
from tokens.models.owner_column import DerivesOwnerFromToken

OWNER_HELP = (
    "Owner, derived from token.company.owner and held directly so a row-level "
    "security policy can read it without joining companies"
)


class FormerHolder(DerivesOwnerFromToken, BaseModel):
    token = models.ForeignKey(
        "tokens.ShareToken",
        on_delete=models.PROTECT,
        related_name="former_holders",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=OWNER_HELP,
    )
    wallet_address = models.CharField(max_length=42, db_index=True)
    ceased_on = models.DateField(db_index=True)
    ceased_at_block = models.BigIntegerField()
    shares_at_cessation = models.DecimalField(max_digits=78, decimal_places=0)
    name = models.CharField(max_length=255, blank=True)
    residential_address = models.TextField(blank=True)
    identity_source = models.CharField(
        max_length=20,
        choices=IDENTITY_SOURCE_CHOICES,
        default=IDENTITY_UNKNOWN,
    )

    class Meta:
        db_table = "tokens_formerholder"
        ordering = ["-ceased_on", "wallet_address"]
        constraints = [
            models.CheckConstraint(condition=models.Q(shares_at_cessation__gt=0), name="former_holder_positive_shares"),
            models.UniqueConstraint(
                fields=("token", "wallet_address", "ceased_at_block"),
                name="one_cessation_per_wallet_per_block",
            ),
        ]
        indexes = [models.Index(fields=["token", "-ceased_on"])]
        verbose_name = "Former holder"
        verbose_name_plural = "Former holders"

    def __str__(self):
        return f"{self.wallet_address} ceased on {self.ceased_on}"
