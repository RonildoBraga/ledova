from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from tokens.exceptions import ChallengeAlreadyUsedException
from tokens.models.owner_column import DerivesWalletFromOrder
from tokens.querysets.signing_challenge import SigningChallengeQuerySet


class SigningChallengePurpose(models.TextChoices):
    ORDER_CANCEL = "order_cancel", "Order cancel"
    ORDER_CREATE = "order_create", "Order create"
    ORDER_MODIFY = "order_modify", "Order modify"


class SigningChallenge(DerivesWalletFromOrder, BaseModel):
    objects = SigningChallengeQuerySet.as_manager()

    purpose = models.CharField(max_length=20, choices=SigningChallengePurpose.choices, db_index=True)
    wallet_address = models.CharField(max_length=42, db_index=True)
    chain_id = models.PositiveBigIntegerField()
    verifying_contract = models.CharField(max_length=42)
    order = models.ForeignKey(
        "tokens.TransferOrder",
        on_delete=models.CASCADE,
        related_name="signing_challenges",
        null=True,
        blank=True,
    )
    submission = models.ForeignKey(
        "tokens.OrderSubmission", on_delete=models.PROTECT, related_name="challenges", null=True, blank=True
    )

    wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text=(
            "Owner. Supplied by the service, which holds the authenticated caller's wallet; "
            "null only for rows written before this column, whose address named no wallet or more than one"
        ),
    )

    payload = models.JSONField()
    digest = models.CharField(max_length=66, unique=True)
    nonce = models.PositiveBigIntegerField()

    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_signature = models.CharField(max_length=132, blank=True)

    class Meta:
        db_table = "signing_challenges"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["wallet_address", "nonce"], name="unique_nonce_per_wallet"),
            models.CheckConstraint(
                condition=(
                    models.Q(consumed_at__isnull=True, consumed_signature="")
                    | (models.Q(consumed_at__isnull=False) & ~models.Q(consumed_signature=""))
                ),
                name="signing_challenge_complete_spend",
            ),
        ]
        indexes = [
            models.Index(fields=["wallet_address", "purpose"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.get_purpose_display()} for {self.wallet_address} ({self.digest[:12]})"

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def mark_consumed(self, signature: str) -> None:
        if self.is_consumed:
            raise ChallengeAlreadyUsedException()

        self.consumed_at = timezone.now()
        self.consumed_signature = signature
        self.save(update_fields=["consumed_at", "consumed_signature", "updated_at"])
