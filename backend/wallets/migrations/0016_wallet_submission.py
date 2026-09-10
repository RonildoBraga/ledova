import uuid

import django.db.models.deletion
from django.db import migrations, models

GUARD = """
CREATE FUNCTION wallets_guard_submission() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Signed wallet submissions cannot be deleted';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF to_jsonb(NEW) - ARRAY['last_attempt_at', 'acknowledged_at', 'updated_at']
            IS DISTINCT FROM to_jsonb(OLD) - ARRAY['last_attempt_at', 'acknowledged_at', 'updated_at'] THEN
            RAISE EXCEPTION 'Signed wallet submission intent cannot be changed';
        END IF;
        IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
            RAISE EXCEPTION 'A wallet submission acknowledgement cannot be changed';
        END IF;
        IF OLD.last_attempt_at IS NOT NULL AND (NEW.last_attempt_at IS NULL OR NEW.last_attempt_at < OLD.last_attempt_at) THEN
            RAISE EXCEPTION 'A wallet submission attempt cannot be rewound';
        END IF;
    ELSE
        IF NOT EXISTS (
            SELECT 1 FROM transactions t JOIN wallets w ON w.uuid = t.wallet_id
             WHERE t.uuid = NEW.transaction_id AND t.wallet_id = NEW.wallet_id
               AND t.user_account_id = NEW.user_account_id AND w.user_account_id = NEW.user_account_id
               AND t.asset_id = NEW.asset_id AND t.tx_hash = NEW.tx_hash AND t.nonce = NEW.nonce
               AND t.chain = NEW.chain AND lower(w.chain) = NEW.chain
               AND lower(t.from_address) = NEW.sender_address AND lower(w.address) = NEW.sender_address
               AND NOT t.imported_from_history AND t.status = 'pending'
               AND t.amount = (NEW.intent->>'amount')::numeric
               AND t.to_address = NEW.intent->>'to_address'
               AND t.transaction_fee_estimated = (NEW.intent->>'maximum_fee')::numeric
        ) OR octet_length(NEW.raw_transaction) = 0 THEN
            RAISE EXCEPTION 'A wallet submission must match its pending transaction and wallet';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_guard_submitted_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'wallets' THEN
        IF EXISTS (SELECT 1 FROM wallets_walletsubmission WHERE wallet_id = OLD.uuid) AND (
            NEW.user_account_id IS DISTINCT FROM OLD.user_account_id
            OR NEW.chain IS DISTINCT FROM OLD.chain OR NEW.address IS DISTINCT FROM OLD.address
        ) THEN
            RAISE EXCEPTION 'A wallet with signed submissions cannot change its identity';
        END IF;
    ELSE
        IF EXISTS (SELECT 1 FROM wallets_walletsubmission WHERE transaction_id = OLD.uuid) AND (
            ROW(NEW.wallet_id, NEW.user_account_id, NEW.tx_hash, NEW.chain, NEW.from_address,
                NEW.to_address, NEW.amount, NEW.asset_id, NEW.nonce, NEW.transaction_fee_estimated, NEW.imported_from_history)
            IS DISTINCT FROM
            ROW(OLD.wallet_id, OLD.user_account_id, OLD.tx_hash, OLD.chain, OLD.from_address,
                OLD.to_address, OLD.amount, OLD.asset_id, OLD.nonce, OLD.transaction_fee_estimated, OLD.imported_from_history)
        ) THEN
            RAISE EXCEPTION 'A submitted transaction cannot change its signed identity';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER wallets_submission_immutable BEFORE INSERT OR UPDATE OR DELETE ON wallets_walletsubmission
FOR EACH ROW EXECUTE FUNCTION wallets_guard_submission();
CREATE TRIGGER wallets_submitted_wallet_identity BEFORE UPDATE ON wallets
FOR EACH ROW EXECUTE FUNCTION wallets_guard_submitted_identity();
CREATE TRIGGER wallets_submitted_transaction_identity BEFORE UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION wallets_guard_submitted_identity();
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from shared.db.policy_sql import install_tables

    install_tables(schema_editor, ["wallets_walletsubmission"])
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(GUARD)


def remove_guards(apps, schema_editor):
    submission = apps.get_model("wallets", "WalletSubmission")
    if submission.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError("Retain signed wallet submissions; this migration cannot discard recorded intent.")
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER wallets_submission_immutable ON wallets_walletsubmission")
        cursor.execute("DROP TRIGGER wallets_submitted_wallet_identity ON wallets")
        cursor.execute("DROP TRIGGER wallets_submitted_transaction_identity ON transactions")
        cursor.execute("DROP FUNCTION wallets_guard_submission()")
        cursor.execute("DROP FUNCTION wallets_guard_submitted_identity()")


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0014_native_chain_deployments"),
        ("users", "0021_trigger_types_from_the_column"),
        ("shared", "0007_review_request_policies"),
        ("wallets", "0015_transaction_imported_from_history"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletSubmission",
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
                ("chain", models.CharField(editable=False, max_length=20)),
                ("chain_id", models.PositiveBigIntegerField(editable=False)),
                ("sender_address", models.CharField(editable=False, max_length=42)),
                ("nonce", models.PositiveBigIntegerField(editable=False)),
                ("tx_hash", models.CharField(editable=False, max_length=66)),
                ("raw_transaction", models.BinaryField()),
                ("intent", models.JSONField(editable=False)),
                ("last_attempt_at", models.DateTimeField(db_index=True, editable=False, null=True)),
                ("acknowledged_at", models.DateTimeField(editable=False, null=True)),
                (
                    "asset",
                    models.ForeignKey(
                        editable=False, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="assets.asset"
                    ),
                ),
                (
                    "deployment",
                    models.ForeignKey(
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="assets.assetchaindeployment",
                    ),
                ),
                (
                    "transaction",
                    models.OneToOneField(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submission",
                        to="wallets.transaction",
                    ),
                ),
                (
                    "user_account",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="users.useraccount",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submissions",
                        to="wallets.wallet",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("wallet", "tx_hash"), name="unique_wallet_submission_hash"),
                    models.UniqueConstraint(
                        fields=("wallet", "chain_id", "nonce"), name="unique_wallet_submission_nonce"
                    ),
                    models.CheckConstraint(condition=models.Q(("chain_id__gt", 0)), name="wallet_submission_chain_id"),
                    models.CheckConstraint(
                        condition=models.Q(("tx_hash__regex", "^0x[0-9a-f]{64}$")), name="wallet_submission_hash"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("sender_address__regex", "^0x[0-9a-f]{40}$")),
                        name="wallet_submission_sender",
                    ),
                ],
            },
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
