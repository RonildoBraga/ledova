import uuid

import django.db.models.deletion
from django.db import migrations, models

TABLES = (
    "blockchain_outgoinghistorycapture",
    "blockchain_outgoinghistoryevidence",
    "blockchain_outgoingcutoverhold",
)

GUARD = """
CREATE FUNCTION blockchain_guard_outgoing_inventory() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Outgoing history observations and cutover holds cannot be changed or deleted';
END;
$$
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from shared.db.policy_sql import install_tables

    install_tables(schema_editor, TABLES)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(GUARD)
        for table in TABLES:
            cursor.execute(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION blockchain_guard_outgoing_inventory()"
            )


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"DROP TRIGGER {table}_immutable ON {table}")
        cursor.execute("DROP FUNCTION blockchain_guard_outgoing_inventory()")


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0004_durable_outgoing"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutgoingHistoryCapture",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("validator_version", models.CharField(editable=False, max_length=32)),
                ("scope", models.JSONField(editable=False)),
                ("manifest_digest", models.CharField(editable=False, max_length=64)),
                ("snapshot_at", models.DateTimeField(editable=False)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("manifest_digest__regex", "^[0-9a-f]{64}$")), name="history_capture_digest"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="OutgoingCutoverHold",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scope",
                    models.CharField(
                        choices=[("signer", "signer"), ("chain", "chain"), ("deployment", "deployment")],
                        editable=False,
                        max_length=16,
                    ),
                ),
                ("observed_chain_id", models.CharField(editable=False, max_length=78, null=True)),
                ("observed_sender", models.CharField(editable=False, max_length=42, null=True)),
                ("hold_key", models.CharField(editable=False, max_length=64)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("missing_raw_payload", "missing_raw_payload"),
                            ("malformed_journal", "malformed_journal"),
                            ("malformed_raw_payload", "malformed_raw_payload"),
                            ("unsupported_envelope", "unsupported_envelope"),
                            ("unsupported_integer_range", "unsupported_integer_range"),
                            ("invalid_signature", "invalid_signature"),
                            ("recorded_hash_mismatch", "recorded_hash_mismatch"),
                            ("mint_terms_mismatch", "mint_terms_mismatch"),
                            ("invalid_source_link", "invalid_source_link"),
                            ("invalid_attempt_identity", "invalid_attempt_identity"),
                            ("current_hash_mismatch", "current_hash_mismatch"),
                            ("missing_chain_provenance", "missing_chain_provenance"),
                            ("missing_signer_authorization", "missing_signer_authorization"),
                            ("unsigned_inflight_snapshot", "unsigned_inflight_snapshot"),
                            ("nonce_payload_conflict", "nonce_payload_conflict"),
                            ("hash_operation_conflict", "hash_operation_conflict"),
                            ("source_identity_conflict", "source_identity_conflict"),
                            ("unjournaled_pause_and_approval", "unjournaled_pause_and_approval"),
                            ("offline_and_old_signers_not_observed", "offline_and_old_signers_not_observed"),
                        ],
                        editable=False,
                        max_length=64,
                    ),
                ),
                ("evidence_refs", models.JSONField(default=list, editable=False)),
                (
                    "capture",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="holds",
                        to="blockchain.outgoinghistorycapture",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("capture", "hold_key"), name="unique_history_capture_hold"),
                    models.CheckConstraint(
                        condition=models.Q(("hold_key__regex", "^[0-9a-f]{64}$")), name="history_hold_digest"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "reason__in",
                                (
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
                                ),
                            )
                        ),
                        name="history_hold_reason",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("observed_chain_id__isnull", True),
                                ("observed_sender__isnull", True),
                                ("scope", "deployment"),
                            ),
                            models.Q(
                                ("observed_chain_id__isnull", False),
                                ("observed_sender__isnull", True),
                                ("scope", "chain"),
                            ),
                            models.Q(
                                ("observed_chain_id__isnull", False),
                                ("observed_sender__isnull", False),
                                ("scope", "signer"),
                            ),
                            _connector="OR",
                        ),
                        name="history_hold_scope_identity",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("observed_chain_id__isnull", True),
                            ("observed_chain_id__regex", "^[1-9][0-9]{0,77}$"),
                            _connector="OR",
                        ),
                        name="history_hold_chain",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("observed_sender__isnull", True),
                            ("observed_sender__regex", "^0x[0-9a-f]{40}$"),
                            _connector="OR",
                        ),
                        name="history_hold_sender",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="OutgoingHistoryEvidence",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier (primary key)",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_model", models.CharField(editable=False, max_length=100)),
                ("source_uuid", models.UUIDField(editable=False)),
                ("entry_key", models.CharField(editable=False, max_length=100)),
                ("source_fingerprint", models.CharField(editable=False, max_length=64)),
                ("identity_fingerprint", models.CharField(editable=False, max_length=64)),
                ("source_snapshot", models.JSONField(editable=False)),
                ("operation_key", models.CharField(blank=True, editable=False, max_length=200)),
                ("raw_transaction", models.BinaryField(null=True)),
                ("observed_hash", models.CharField(blank=True, editable=False, max_length=66)),
                ("observed_chain_id", models.CharField(editable=False, max_length=78, null=True)),
                ("observed_sender", models.CharField(editable=False, max_length=42, null=True)),
                ("observed_nonce", models.CharField(editable=False, max_length=78, null=True)),
                ("expected_terms", models.JSONField(default=dict, editable=False)),
                ("decoded_intent", models.JSONField(default=dict, editable=False)),
                ("raw_valid", models.BooleanField(default=False, editable=False)),
                ("terms_match", models.BooleanField(default=False, editable=False)),
                ("source_link_valid", models.BooleanField(default=False, editable=False)),
                ("proved_unsigned", models.BooleanField(default=False, editable=False)),
                ("findings", models.JSONField(default=list, editable=False)),
                (
                    "capture",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="evidence",
                        to="blockchain.outgoinghistorycapture",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["observed_chain_id", "observed_sender", "observed_nonce"],
                        name="history_observed_nonce_idx",
                    ),
                    models.Index(fields=["observed_hash"], name="history_observed_hash_idx"),
                    models.Index(fields=["source_model", "source_uuid", "entry_key"], name="history_source_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("capture", "source_model", "source_uuid", "entry_key", "source_fingerprint"),
                        name="unique_history_source_observation",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("identity_fingerprint__regex", "^[0-9a-f]{64}$"),
                            ("source_fingerprint__regex", "^[0-9a-f]{64}$"),
                        ),
                        name="history_evidence_digests",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("observed_hash", ""), ("observed_hash__regex", "^0x[0-9a-f]{64}$"), _connector="OR"
                        ),
                        name="history_observed_hash",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("observed_chain_id__isnull", True),
                            ("observed_chain_id__regex", "^[1-9][0-9]{0,77}$"),
                            _connector="OR",
                        ),
                        name="history_observed_chain",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("observed_sender__isnull", True),
                            ("observed_sender__regex", "^0x[0-9a-f]{40}$"),
                            _connector="OR",
                        ),
                        name="history_observed_sender",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("observed_nonce__isnull", True),
                            ("observed_nonce__regex", "^(0|[1-9][0-9]{0,77})$"),
                            _connector="OR",
                        ),
                        name="history_observed_nonce",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("raw_valid", False),
                            models.Q(
                                ("observed_chain_id__isnull", False),
                                ("observed_hash__regex", "^0x[0-9a-f]{64}$"),
                                ("observed_nonce__isnull", False),
                                ("observed_sender__isnull", False),
                                ("raw_transaction__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="history_valid_raw_has_identity",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("terms_match", False),
                            models.Q(
                                ("raw_valid", True),
                                models.Q(("expected_terms", {}), _negated=True),
                                models.Q(("decoded_intent", {}), _negated=True),
                            ),
                            _connector="OR",
                        ),
                        name="history_matching_terms_have_raw",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("source_link_valid", False),
                            models.Q(("operation_key", ""), _negated=True),
                            _connector="OR",
                        ),
                        name="history_link_has_operation",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("proved_unsigned", False),
                            models.Q(
                                ("observed_chain_id__isnull", True),
                                ("observed_hash", ""),
                                ("observed_nonce__isnull", True),
                                ("observed_sender__isnull", True),
                                ("raw_transaction__isnull", True),
                                ("raw_valid", False),
                                ("source_link_valid", True),
                            ),
                            _connector="OR",
                        ),
                        name="history_unsigned_has_no_payload",
                    ),
                ],
            },
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
