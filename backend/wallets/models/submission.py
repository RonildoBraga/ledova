from django.db import models

from shared.models import BaseModel

DELIVERY_FIELDS = frozenset({"last_attempt_at", "acknowledged_at", "updated_at"})


class SubmissionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if set(kwargs) - DELIVERY_FIELDS:
            raise ValueError("Signed wallet submission intent cannot be changed.")
        return super().update(**kwargs)

    def delete(self):
        raise ValueError("Signed wallet submissions cannot be deleted.")


class WalletSubmission(BaseModel):
    wallet = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT, related_name="submissions", editable=False)
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+", editable=False)
    transaction = models.OneToOneField(
        "wallets.Transaction", on_delete=models.PROTECT, related_name="submission", editable=False
    )
    asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="+", editable=False)
    deployment = models.ForeignKey(
        "assets.AssetChainDeployment", on_delete=models.PROTECT, null=True, related_name="+", editable=False
    )
    chain = models.CharField(max_length=20, editable=False)
    chain_id = models.PositiveBigIntegerField(editable=False)
    sender_address = models.CharField(max_length=42, editable=False)
    nonce = models.PositiveBigIntegerField(editable=False)
    tx_hash = models.CharField(max_length=66, editable=False)
    raw_transaction = models.BinaryField(editable=False)
    intent = models.JSONField(editable=False)
    last_attempt_at = models.DateTimeField(null=True, editable=False, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, editable=False)

    objects = SubmissionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["wallet", "tx_hash"], name="unique_wallet_submission_hash"),
            models.UniqueConstraint(fields=["wallet", "chain_id", "nonce"], name="unique_wallet_submission_nonce"),
            models.UniqueConstraint(fields=["chain_id", "tx_hash"], name="unique_submission_chain_hash"),
            models.UniqueConstraint(
                fields=["chain_id", "sender_address", "nonce"], name="unique_submission_sender_nonce"
            ),
            models.CheckConstraint(condition=models.Q(chain_id__gt=0), name="wallet_submission_chain_id"),
            models.CheckConstraint(
                condition=models.Q(tx_hash__regex=r"^0x[0-9a-f]{64}$"), name="wallet_submission_hash"
            ),
            models.CheckConstraint(
                condition=models.Q(sender_address__regex=r"^0x[0-9a-f]{40}$"), name="wallet_submission_sender"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = kwargs.get("update_fields")
            if not fields or set(fields) - DELIVERY_FIELDS:
                raise ValueError("Signed wallet submission intent cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Signed wallet submissions cannot be deleted.")

    def __str__(self):
        return self.tx_hash
