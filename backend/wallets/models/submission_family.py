from django.db import models

from shared.models import BaseModel
from wallets.models.chain_observation import ChainObservationQuerySet

FAMILY_STATE_FIELDS = frozenset(
    {
        "selected",
        "selected_id",
        "winner",
        "winner_id",
        "winner_observation",
        "winner_observation_id",
        "generation",
        "native_exposure",
        "token_exposure",
        "updated_at",
    }
)


class SubmissionFamilyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if set(kwargs) - FAMILY_STATE_FIELDS:
            raise ValueError("A submission family cannot change its original identity.")
        return super().update(**kwargs)

    def delete(self):
        raise ValueError("Submission families cannot be deleted.")


class WalletSubmissionFamily(BaseModel):
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="submission_families")
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+")
    chain = models.CharField(max_length=20, editable=False)
    chain_id = models.PositiveBigIntegerField(editable=False)
    sender_address = models.CharField(max_length=42, editable=False)
    nonce = models.PositiveBigIntegerField(editable=False)
    asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="+")
    deployment = models.ForeignKey("assets.AssetChainDeployment", on_delete=models.PROTECT, null=True, related_name="+")
    original_tx_hash = models.CharField(max_length=66, editable=False)
    original_intent = models.JSONField(editable=False)
    selected = models.ForeignKey("wallets.WalletSubmission", on_delete=models.PROTECT, null=True, related_name="+")
    winner = models.ForeignKey("wallets.WalletSubmission", on_delete=models.PROTECT, null=True, related_name="+")
    winner_observation = models.ForeignKey(
        "wallets.WalletChainObservation", on_delete=models.PROTECT, null=True, related_name="+"
    )
    generation = models.PositiveBigIntegerField(default=0, editable=False)
    native_exposure = models.DecimalField(max_digits=40, decimal_places=18)
    token_exposure = models.DecimalField(max_digits=40, decimal_places=18, default=0)

    objects = SubmissionFamilyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["wallet", "chain_id", "nonce"], name="unique_wallet_family_nonce"),
            models.UniqueConstraint(fields=["chain_id", "sender_address", "nonce"], name="unique_family_sender_nonce"),
            models.CheckConstraint(condition=models.Q(chain_id__gt=0), name="wallet_family_chain_id"),
            models.CheckConstraint(
                condition=models.Q(native_exposure__gte=0, token_exposure__gte=0), name="wallet_family_exposure"
            ),
            models.CheckConstraint(
                condition=models.Q(sender_address__regex=r"^0x[0-9a-f]{40}$"), name="wallet_family_sender"
            ),
            models.CheckConstraint(
                condition=models.Q(original_tx_hash__regex=r"^0x[0-9a-f]{64}$"), name="wallet_family_hash"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = kwargs.get("update_fields")
            if not fields or set(fields) - FAMILY_STATE_FIELDS:
                raise ValueError("A submission family cannot change its original identity.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Submission families cannot be deleted.")


class WalletBalanceProjection(BaseModel):
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="balance_projections")
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+")
    observation = models.JSONField(editable=False)
    reservations = models.JSONField(editable=False)
    quantities = models.JSONField(editable=False)

    objects = ChainObservationQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Balance projections cannot be rewritten.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Balance projections cannot be deleted.")
