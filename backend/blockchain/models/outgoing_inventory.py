from django.core.exceptions import ValidationError
from django.db import models

from shared.models import BaseModel

FINDINGS = (
    "missing_raw_payload",
    "malformed_journal",
    "malformed_raw_payload",
    "unsupported_envelope",
    "unsupported_integer_range",
    "invalid_signature",
    "recorded_hash_mismatch",
    "mint_terms_mismatch",
    "invalid_source_link",
    "invalid_attempt_identity",
    "current_hash_mismatch",
    "missing_chain_provenance",
    "missing_signer_authorization",
    "unsigned_inflight_snapshot",
    "nonce_payload_conflict",
    "hash_operation_conflict",
    "source_identity_conflict",
    "unjournaled_pause_and_approval",
    "offline_and_old_signers_not_observed",
)


class ImmutableInventoryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Outgoing history observations cannot be changed.")

    def delete(self):
        raise ValueError("Outgoing history observations cannot be deleted.")


class ImmutableInventory(BaseModel):
    objects = ImmutableInventoryQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Outgoing history observations cannot be changed.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Outgoing history observations cannot be deleted.")

    def __str__(self):
        return str(self.pk)


class OutgoingHistoryCapture(ImmutableInventory):
    validator_version = models.CharField(max_length=32, editable=False)
    scope = models.JSONField(editable=False)
    manifest_digest = models.CharField(max_length=64, editable=False)
    snapshot_at = models.DateTimeField(editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(manifest_digest__regex=r"^[0-9a-f]{64}$"), name="history_capture_digest"
            ),
        ]


class OutgoingHistoryEvidence(ImmutableInventory):
    capture = models.ForeignKey(
        OutgoingHistoryCapture, on_delete=models.PROTECT, related_name="evidence", editable=False
    )
    source_model = models.CharField(max_length=100, editable=False)
    source_uuid = models.UUIDField(editable=False)
    entry_key = models.CharField(max_length=100, editable=False)
    source_fingerprint = models.CharField(max_length=64, editable=False)
    identity_fingerprint = models.CharField(max_length=64, editable=False)
    source_snapshot = models.JSONField(editable=False)
    operation_key = models.CharField(max_length=200, blank=True, editable=False)
    raw_transaction = models.BinaryField(null=True, editable=False)
    observed_hash = models.CharField(max_length=66, blank=True, editable=False)
    observed_chain_id = models.CharField(max_length=78, null=True, editable=False)
    observed_sender = models.CharField(max_length=42, null=True, editable=False)
    observed_nonce = models.CharField(max_length=78, null=True, editable=False)
    expected_terms = models.JSONField(default=dict, editable=False)
    decoded_intent = models.JSONField(default=dict, editable=False)
    raw_valid = models.BooleanField(default=False, editable=False)
    terms_match = models.BooleanField(default=False, editable=False)
    source_link_valid = models.BooleanField(default=False, editable=False)
    proved_unsigned = models.BooleanField(default=False, editable=False)
    findings = models.JSONField(default=list, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["capture", "source_model", "source_uuid", "entry_key", "source_fingerprint"],
                name="unique_history_source_observation",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    source_fingerprint__regex=r"^[0-9a-f]{64}$", identity_fingerprint__regex=r"^[0-9a-f]{64}$"
                ),
                name="history_evidence_digests",
            ),
            models.CheckConstraint(
                condition=models.Q(observed_hash="") | models.Q(observed_hash__regex=r"^0x[0-9a-f]{64}$"),
                name="history_observed_hash",
            ),
            models.CheckConstraint(
                condition=models.Q(observed_chain_id__isnull=True)
                | models.Q(observed_chain_id__regex=r"^[1-9][0-9]{0,77}$"),
                name="history_observed_chain",
            ),
            models.CheckConstraint(
                condition=models.Q(observed_sender__isnull=True) | models.Q(observed_sender__regex=r"^0x[0-9a-f]{40}$"),
                name="history_observed_sender",
            ),
            models.CheckConstraint(
                condition=models.Q(observed_nonce__isnull=True)
                | models.Q(observed_nonce__regex=r"^(0|[1-9][0-9]{0,77})$"),
                name="history_observed_nonce",
            ),
            models.CheckConstraint(
                condition=models.Q(raw_valid=False)
                | models.Q(
                    raw_transaction__isnull=False,
                    observed_hash__regex=r"^0x[0-9a-f]{64}$",
                    observed_chain_id__isnull=False,
                    observed_sender__isnull=False,
                    observed_nonce__isnull=False,
                ),
                name="history_valid_raw_has_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(terms_match=False)
                | (models.Q(raw_valid=True) & ~models.Q(expected_terms={}) & ~models.Q(decoded_intent={})),
                name="history_matching_terms_have_raw",
            ),
            models.CheckConstraint(
                condition=models.Q(source_link_valid=False) | ~models.Q(operation_key=""),
                name="history_link_has_operation",
            ),
            models.CheckConstraint(
                condition=models.Q(proved_unsigned=False)
                | models.Q(
                    raw_transaction__isnull=True,
                    observed_hash="",
                    observed_chain_id__isnull=True,
                    observed_sender__isnull=True,
                    observed_nonce__isnull=True,
                    raw_valid=False,
                    source_link_valid=True,
                ),
                name="history_unsigned_has_no_payload",
            ),
        ]
        indexes = [
            models.Index(
                fields=["observed_chain_id", "observed_sender", "observed_nonce"], name="history_observed_nonce_idx"
            ),
            models.Index(fields=["observed_hash"], name="history_observed_hash_idx"),
            models.Index(fields=["source_model", "source_uuid", "entry_key"], name="history_source_idx"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.findings, list) or any(code not in FINDINGS for code in self.findings):
            raise ValidationError("Outgoing history findings are invalid.")


class OutgoingCutoverHold(ImmutableInventory):
    capture = models.ForeignKey(OutgoingHistoryCapture, on_delete=models.PROTECT, related_name="holds", editable=False)
    scope = models.CharField(
        max_length=16, choices=[(value, value) for value in ("signer", "chain", "deployment")], editable=False
    )
    observed_chain_id = models.CharField(max_length=78, null=True, editable=False)
    observed_sender = models.CharField(max_length=42, null=True, editable=False)
    hold_key = models.CharField(max_length=64, editable=False)
    reason = models.CharField(max_length=64, choices=[(value, value) for value in FINDINGS], editable=False)
    evidence_refs = models.JSONField(default=list, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["capture", "hold_key"], name="unique_history_capture_hold"),
            models.CheckConstraint(condition=models.Q(hold_key__regex=r"^[0-9a-f]{64}$"), name="history_hold_digest"),
            models.CheckConstraint(condition=models.Q(reason__in=FINDINGS), name="history_hold_reason"),
            models.CheckConstraint(
                condition=models.Q(scope="deployment", observed_chain_id__isnull=True, observed_sender__isnull=True)
                | models.Q(scope="chain", observed_chain_id__isnull=False, observed_sender__isnull=True)
                | models.Q(scope="signer", observed_chain_id__isnull=False, observed_sender__isnull=False),
                name="history_hold_scope_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(observed_chain_id__isnull=True)
                | models.Q(observed_chain_id__regex=r"^[1-9][0-9]{0,77}$"),
                name="history_hold_chain",
            ),
            models.CheckConstraint(
                condition=models.Q(observed_sender__isnull=True) | models.Q(observed_sender__regex=r"^0x[0-9a-f]{40}$"),
                name="history_hold_sender",
            ),
        ]
