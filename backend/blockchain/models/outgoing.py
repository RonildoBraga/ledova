from django.db import models

from blockchain.constants import MAX_SIGNER_ADMISSION_GENERATION
from shared.models import BaseModel


class OutgoingStatus(models.TextChoices):
    PREPARING = "preparing", "Preparing"
    SIGNED = "signed", "Signed; outcome unresolved"
    CONFIRMED = "confirmed", "Confirmed"
    REVERTED = "reverted", "Reverted"
    FAILED = "failed", "Failed before signing"


class SignerAdmission(models.TextChoices):
    CLOSED = "closed", "Closed"
    ADMITTED = "admitted", "Admitted"


class SigningAccount(BaseModel):
    chain_id = models.PositiveBigIntegerField(editable=False)
    address = models.CharField(max_length=42, editable=False)
    next_nonce = models.PositiveBigIntegerField(default=0, editable=False)
    admission_state = models.CharField(
        max_length=8, choices=SignerAdmission.choices, default=SignerAdmission.CLOSED, editable=False
    )
    admission_generation = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chain_id", "address"], name="unique_outgoing_signer"),
            models.CheckConstraint(
                condition=models.Q(address__regex=r"^0x[0-9a-f]{40}$"), name="outgoing_signer_address"
            ),
            models.CheckConstraint(condition=models.Q(chain_id__gt=0), name="outgoing_signer_chain"),
            models.CheckConstraint(
                condition=(
                    models.Q(admission_state=SignerAdmission.CLOSED)
                    | models.Q(
                        admission_state=SignerAdmission.ADMITTED,
                        admission_generation__gt=0,
                        admission_generation__lt=MAX_SIGNER_ADMISSION_GENERATION,
                    )
                ),
                name="outgoing_signer_admission",
            ),
        ]

    def __str__(self):
        return f"{self.chain_id}:{self.address}"


class OutgoingOperation(BaseModel):
    operation_key = models.CharField(max_length=200, unique=True, editable=False)
    intent = models.JSONField(editable=False)
    claim_id = models.UUIDField(editable=False)
    status = models.CharField(max_length=16, choices=OutgoingStatus.choices, default=OutgoingStatus.PREPARING)
    current_attempt = models.ForeignKey(
        "blockchain.SignedAttempt", on_delete=models.PROTECT, null=True, blank=True, related_name="+", editable=False
    )
    last_error = models.CharField(max_length=100, blank=True, editable=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True, editable=False)
    block_number = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    block_hash = models.CharField(max_length=66, blank=True, editable=False)
    gas_used = models.PositiveBigIntegerField(null=True, blank=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status__in=[OutgoingStatus.PREPARING, OutgoingStatus.FAILED], current_attempt__isnull=True)
                    | models.Q(
                        status__in=[OutgoingStatus.SIGNED, OutgoingStatus.CONFIRMED, OutgoingStatus.REVERTED],
                        current_attempt__isnull=False,
                    )
                ),
                name="outgoing_status_has_attempt",
            ),
        ]

    def __str__(self):
        return f"{self.operation_key} ({self.status})"


class ImmutableAttemptQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Signed transaction attempts cannot be changed.")

    def delete(self):
        raise ValueError("Signed transaction attempts cannot be deleted.")


class SignedAttempt(BaseModel):
    operation = models.ForeignKey(OutgoingOperation, on_delete=models.PROTECT, related_name="attempts", editable=False)
    claim_id = models.UUIDField(editable=False)
    signer = models.ForeignKey(SigningAccount, on_delete=models.PROTECT, related_name="attempts", editable=False)
    nonce = models.PositiveBigIntegerField(editable=False)
    tx_hash = models.CharField(max_length=66, unique=True, editable=False)
    raw_transaction = models.BinaryField(editable=False)

    objects = ImmutableAttemptQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["signer", "nonce"], name="unique_outgoing_signer_nonce"),
            models.UniqueConstraint(fields=["operation", "claim_id"], name="unique_outgoing_signed_claim"),
            models.CheckConstraint(
                condition=models.Q(tx_hash__regex=r"^0x[0-9a-f]{64}$"), name="outgoing_attempt_hash"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Signed transaction attempts cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Signed transaction attempts cannot be deleted.")

    def __str__(self):
        return self.tx_hash
