from django.db import models

from shared.models import BaseModel
from wallets.models.submission import DELIVERY_FIELDS, SubmissionQuerySet


class BitcoinNetwork(models.TextChoices):
    TEST = "test", "test"
    REGTEST = "regtest", "regtest"


class BitcoinSubmission(BaseModel):
    wallet = models.ForeignKey(
        "wallets.Wallet", on_delete=models.PROTECT, related_name="bitcoin_submissions", editable=False
    )
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+", editable=False)
    transaction = models.OneToOneField(
        "wallets.Transaction", on_delete=models.PROTECT, related_name="bitcoin_submission", editable=False
    )
    asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="+", editable=False)
    network = models.CharField(max_length=10, choices=BitcoinNetwork.choices, editable=False)
    genesis_hash = models.CharField(max_length=64, editable=False)
    sender_address = models.CharField(max_length=255, editable=False)
    tx_hash = models.CharField(max_length=64, editable=False)
    witness_hash = models.CharField(max_length=64, editable=False)
    raw_transaction = models.BinaryField(editable=False)
    intent = models.JSONField(editable=False)
    last_attempt_at = models.DateTimeField(null=True, editable=False, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, editable=False)

    objects = SubmissionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["network", "tx_hash"], name="unique_bitcoin_submission_hash"),
            models.CheckConstraint(
                condition=models.Q(network__in=BitcoinNetwork.values), name="bitcoin_submission_network"
            ),
            models.CheckConstraint(
                condition=models.Q(tx_hash__regex=r"^[0-9a-f]{64}$"), name="bitcoin_submission_hash"
            ),
            models.CheckConstraint(
                condition=models.Q(witness_hash__regex=r"^[0-9a-f]{64}$"), name="bitcoin_submission_witness"
            ),
            models.CheckConstraint(
                condition=models.Q(genesis_hash__regex=r"^[0-9a-f]{64}$"), name="bitcoin_submission_genesis"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = kwargs.get("update_fields")
            if not fields or set(fields) - DELIVERY_FIELDS:
                raise ValueError("Signed Bitcoin submission intent cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Signed Bitcoin submissions cannot be deleted.")

    def __str__(self):
        return self.tx_hash


class BitcoinInputQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Recorded Bitcoin inputs cannot be changed.")

    def delete(self):
        raise ValueError("Recorded Bitcoin inputs cannot be deleted.")


class BitcoinSubmissionInput(BaseModel):
    submission = models.ForeignKey(BitcoinSubmission, on_delete=models.PROTECT, related_name="inputs", editable=False)
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="+", editable=False)
    network = models.CharField(max_length=10, editable=False)
    previous_tx_hash = models.CharField(max_length=64, editable=False)
    output_index = models.PositiveBigIntegerField(editable=False)
    satoshis = models.PositiveBigIntegerField(editable=False)
    script = models.BinaryField(editable=False)
    observed_block_hash = models.CharField(max_length=64, editable=False)

    objects = BitcoinInputQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["network", "previous_tx_hash", "output_index"], name="unique_bitcoin_submission_input"
            ),
            models.CheckConstraint(condition=models.Q(output_index__lt=2**32), name="bitcoin_submission_input_index"),
            models.CheckConstraint(condition=models.Q(satoshis__lte=2_100_000_000_000_000), name="bitcoin_input_value"),
            models.CheckConstraint(
                condition=models.Q(previous_tx_hash__regex=r"^[0-9a-f]{64}$"), name="bitcoin_input_hash"
            ),
            models.CheckConstraint(
                condition=models.Q(observed_block_hash__regex=r"^[0-9a-f]{64}$"), name="bitcoin_input_block"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Recorded Bitcoin inputs cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Recorded Bitcoin inputs cannot be deleted.")
