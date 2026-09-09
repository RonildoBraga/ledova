import uuid

import django.db.models.deletion
from django.db import migrations, models

TABLES = ("blockchain_outgoingoperation", "blockchain_signingaccount", "blockchain_signedattempt")

GUARD = """
CREATE FUNCTION blockchain_guard_outgoing_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR TG_TABLE_NAME = 'blockchain_signedattempt' THEN
        RAISE EXCEPTION 'Outgoing transaction history cannot be changed or deleted';
    END IF;
    IF TG_TABLE_NAME = 'blockchain_signingaccount' THEN
        IF NEW.chain_id IS DISTINCT FROM OLD.chain_id OR NEW.address IS DISTINCT FROM OLD.address
           OR NEW.next_nonce < OLD.next_nonce THEN
            RAISE EXCEPTION 'Outgoing signer identity and reserved nonces cannot be rewound';
        END IF;
    ELSE
        IF NEW.operation_key IS DISTINCT FROM OLD.operation_key OR NEW.intent IS DISTINCT FROM OLD.intent THEN
            RAISE EXCEPTION 'Outgoing operation identity cannot be changed';
        END IF;
        IF NEW.claim_id IS DISTINCT FROM OLD.claim_id THEN
            IF OLD.status NOT IN ('failed', 'reverted') OR NEW.status <> 'preparing'
               OR NEW.current_attempt_id IS NOT NULL THEN
                RAISE EXCEPTION 'Only a proved unsuccessful outgoing attempt can be restarted';
            END IF;
        ELSIF (OLD.status IN ('failed', 'confirmed', 'reverted') AND NEW.status <> OLD.status)
           OR (OLD.status = 'signed' AND NEW.status NOT IN ('signed', 'confirmed', 'reverted'))
           OR (OLD.status = 'preparing' AND NEW.status NOT IN ('preparing', 'signed', 'failed'))
           OR (OLD.current_attempt_id IS NOT NULL AND NEW.current_attempt_id IS DISTINCT FROM OLD.current_attempt_id)
        THEN
            RAISE EXCEPTION 'The outgoing attempt cannot be replaced or rewound';
        END IF;
        IF NEW.current_attempt_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM blockchain_signedattempt
             WHERE uuid = NEW.current_attempt_id AND operation_id = NEW.uuid AND claim_id = NEW.claim_id
        ) THEN
            RAISE EXCEPTION 'The outgoing operation must identify its own signed attempt';
        END IF;
    END IF;
    RETURN NEW;
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
                f"CREATE TRIGGER {table}_identity BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION blockchain_guard_outgoing_identity()"
            )


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"DROP TRIGGER {table}_identity ON {table}")
        cursor.execute("DROP FUNCTION blockchain_guard_outgoing_identity()")


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0003_delete_contractdeployment"),
        ("shared", "0003_rls_roles_and_grants"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutgoingOperation",
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
                ("operation_key", models.CharField(editable=False, max_length=200, unique=True)),
                ("intent", models.JSONField(editable=False)),
                ("claim_id", models.UUIDField(editable=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("preparing", "Preparing"),
                            ("signed", "Signed; outcome unresolved"),
                            ("confirmed", "Confirmed"),
                            ("reverted", "Reverted"),
                            ("failed", "Failed before signing"),
                        ],
                        default="preparing",
                        max_length=16,
                    ),
                ),
                ("last_error", models.CharField(blank=True, editable=False, max_length=100)),
                ("acknowledged_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("block_number", models.PositiveBigIntegerField(blank=True, editable=False, null=True)),
                ("block_hash", models.CharField(blank=True, editable=False, max_length=66)),
                ("gas_used", models.PositiveBigIntegerField(blank=True, editable=False, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="SignedAttempt",
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
                ("claim_id", models.UUIDField(editable=False)),
                ("nonce", models.PositiveBigIntegerField(editable=False)),
                ("tx_hash", models.CharField(editable=False, max_length=66, unique=True)),
                ("raw_transaction", models.BinaryField()),
                (
                    "operation",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="attempts",
                        to="blockchain.outgoingoperation",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="outgoingoperation",
            name="current_attempt",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="blockchain.signedattempt",
            ),
        ),
        migrations.CreateModel(
            name="SigningAccount",
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
                ("chain_id", models.PositiveBigIntegerField(editable=False)),
                ("address", models.CharField(editable=False, max_length=42)),
                ("next_nonce", models.PositiveBigIntegerField(default=0, editable=False)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("chain_id", "address"), name="unique_outgoing_signer"),
                    models.CheckConstraint(
                        condition=models.Q(("address__regex", "^0x[0-9a-f]{40}$")), name="outgoing_signer_address"
                    ),
                    models.CheckConstraint(condition=models.Q(("chain_id__gt", 0)), name="outgoing_signer_chain"),
                ],
            },
        ),
        migrations.AddField(
            model_name="signedattempt",
            name="signer",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempts",
                to="blockchain.signingaccount",
            ),
        ),
        migrations.AddConstraint(
            model_name="outgoingoperation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("current_attempt__isnull", True), ("status__in", ["preparing", "failed"])),
                    models.Q(("current_attempt__isnull", False), ("status__in", ["signed", "confirmed", "reverted"])),
                    _connector="OR",
                ),
                name="outgoing_status_has_attempt",
            ),
        ),
        migrations.AddConstraint(
            model_name="signedattempt",
            constraint=models.UniqueConstraint(fields=("signer", "nonce"), name="unique_outgoing_signer_nonce"),
        ),
        migrations.AddConstraint(
            model_name="signedattempt",
            constraint=models.UniqueConstraint(fields=("operation", "claim_id"), name="unique_outgoing_signed_claim"),
        ),
        migrations.AddConstraint(
            model_name="signedattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(("tx_hash__regex", "^0x[0-9a-f]{64}$")), name="outgoing_attempt_hash"
            ),
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
