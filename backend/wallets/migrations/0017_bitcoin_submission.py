import uuid

import django.db.models.deletion
from django.db import migrations, models

GUARD = """
CREATE FUNCTION wallets_guard_bitcoin_submission() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Signed Bitcoin submissions cannot be deleted';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF to_jsonb(NEW) - ARRAY['last_attempt_at', 'acknowledged_at', 'updated_at']
            IS DISTINCT FROM to_jsonb(OLD) - ARRAY['last_attempt_at', 'acknowledged_at', 'updated_at'] THEN
            RAISE EXCEPTION 'Signed Bitcoin submission intent cannot be changed';
        END IF;
        IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
            RAISE EXCEPTION 'A Bitcoin submission acknowledgement cannot be changed';
        END IF;
        IF OLD.last_attempt_at IS NOT NULL AND (NEW.last_attempt_at IS NULL OR NEW.last_attempt_at < OLD.last_attempt_at) THEN
            RAISE EXCEPTION 'A Bitcoin submission attempt cannot be rewound';
        END IF;
    ELSE
        IF NOT EXISTS (
            SELECT 1 FROM transactions t JOIN wallets w ON w.uuid = t.wallet_id
             WHERE t.uuid = NEW.transaction_id AND t.wallet_id = NEW.wallet_id
               AND t.user_account_id = NEW.user_account_id AND w.user_account_id = NEW.user_account_id
               AND t.asset_id = NEW.asset_id AND t.tx_hash = NEW.tx_hash AND t.nonce IS NULL
               AND t.chain = 'bitcoin' AND lower(w.chain) = 'bitcoin'
               AND t.from_address = NEW.sender_address AND w.address = NEW.sender_address
               AND NOT t.imported_from_history AND t.status = 'pending'
               AND t.amount = (NEW.intent->>'amount_satoshis')::numeric / 100000000
               AND t.to_address = NEW.intent->>'to_address'
               AND t.transaction_fee_estimated = (NEW.intent->>'fee_satoshis')::numeric / 100000000
               AND NEW.intent->>'network' = NEW.network
               AND NEW.intent->>'genesis_hash' = NEW.genesis_hash
               AND NEW.intent->>'sender_address' = NEW.sender_address
               AND (NEW.intent->>'amount_satoshis')::numeric > 0
               AND (NEW.intent->>'fee_satoshis')::numeric >= 0
               AND jsonb_typeof(NEW.intent->'inputs') = 'array'
               AND jsonb_array_length(NEW.intent->'inputs') BETWEEN 1 AND 1000
               AND octet_length(NEW.raw_transaction) BETWEEN 10 AND 400000
               AND NEW.genesis_hash = CASE NEW.network
                   WHEN 'test' THEN '000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943'
                   WHEN 'regtest' THEN '0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206'
               END
        ) OR EXISTS (
            SELECT 1 FROM wallets_bitcoinsubmission s WHERE s.wallet_id = NEW.wallet_id AND s.network <> NEW.network
        ) THEN
            RAISE EXCEPTION 'A Bitcoin submission must match its pending transaction, wallet and network';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_guard_bitcoin_input() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Recorded Bitcoin inputs cannot be changed or deleted';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM wallets_bitcoinsubmission s, jsonb_array_elements(s.intent->'inputs') AS item
         WHERE s.uuid = NEW.submission_id AND s.user_account_id = NEW.user_account_id AND s.network = NEW.network
           AND item->>'tx_hash' = NEW.previous_tx_hash
           AND (item->>'output_index')::bigint = NEW.output_index
           AND (item->>'satoshis')::bigint = NEW.satoshis
           AND item->>'script' = encode(NEW.script, 'hex')
           AND item->>'observed_block_hash' = NEW.observed_block_hash
    ) THEN
        RAISE EXCEPTION 'A Bitcoin input must match its recorded signed intent and owner';
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_require_bitcoin_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT count(*) FROM wallets_bitcoinsubmissioninput WHERE submission_id = NEW.uuid)
        <> jsonb_array_length(NEW.intent->'inputs') THEN
        RAISE EXCEPTION 'A Bitcoin submission requires every recorded input reservation';
    END IF;
    RETURN NULL;
END;
$$;
CREATE FUNCTION wallets_guard_bitcoin_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'wallets' THEN
        IF EXISTS (SELECT 1 FROM wallets_bitcoinsubmission WHERE wallet_id = OLD.uuid) AND (
            NEW.user_account_id IS DISTINCT FROM OLD.user_account_id
            OR NEW.chain IS DISTINCT FROM OLD.chain OR NEW.address IS DISTINCT FROM OLD.address
        ) THEN
            RAISE EXCEPTION 'A wallet with signed Bitcoin submissions cannot change its identity';
        END IF;
    ELSE
        IF EXISTS (SELECT 1 FROM wallets_bitcoinsubmission WHERE transaction_id = OLD.uuid) AND (
            ROW(NEW.wallet_id, NEW.user_account_id, NEW.tx_hash, NEW.chain, NEW.from_address,
                NEW.to_address, NEW.amount, NEW.asset_id, NEW.nonce, NEW.transaction_fee_estimated, NEW.imported_from_history)
            IS DISTINCT FROM
            ROW(OLD.wallet_id, OLD.user_account_id, OLD.tx_hash, OLD.chain, OLD.from_address,
                OLD.to_address, OLD.amount, OLD.asset_id, OLD.nonce, OLD.transaction_fee_estimated, OLD.imported_from_history)
        ) THEN
            RAISE EXCEPTION 'A submitted Bitcoin transaction cannot change its signed identity';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER wallets_bitcoin_submission_immutable BEFORE INSERT OR UPDATE OR DELETE ON wallets_bitcoinsubmission
FOR EACH ROW EXECUTE FUNCTION wallets_guard_bitcoin_submission();
CREATE TRIGGER wallets_bitcoin_input_immutable BEFORE INSERT OR UPDATE OR DELETE ON wallets_bitcoinsubmissioninput
FOR EACH ROW EXECUTE FUNCTION wallets_guard_bitcoin_input();
CREATE CONSTRAINT TRIGGER wallets_bitcoin_complete_inputs AFTER INSERT ON wallets_bitcoinsubmission
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION wallets_require_bitcoin_inputs();
CREATE TRIGGER wallets_bitcoin_wallet_identity BEFORE UPDATE ON wallets
FOR EACH ROW EXECUTE FUNCTION wallets_guard_bitcoin_identity();
CREATE TRIGGER wallets_bitcoin_transaction_identity BEFORE UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION wallets_guard_bitcoin_identity();
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from shared.db.policy_sql import install_tables

    install_tables(schema_editor, ["wallets_bitcoinsubmission", "wallets_bitcoinsubmissioninput"])
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(GUARD)


def remove_guards(apps, schema_editor):
    for name in ("BitcoinSubmission", "BitcoinSubmissionInput"):
        model = apps.get_model("wallets", name)
        if model.objects.using(schema_editor.connection.alias).exists():
            raise RuntimeError("Retain signed Bitcoin submissions; this migration cannot discard recorded intent.")
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER wallets_bitcoin_submission_immutable ON wallets_bitcoinsubmission")
        cursor.execute("DROP TRIGGER wallets_bitcoin_input_immutable ON wallets_bitcoinsubmissioninput")
        cursor.execute("DROP TRIGGER wallets_bitcoin_complete_inputs ON wallets_bitcoinsubmission")
        cursor.execute("DROP TRIGGER wallets_bitcoin_wallet_identity ON wallets")
        cursor.execute("DROP TRIGGER wallets_bitcoin_transaction_identity ON transactions")
        cursor.execute("DROP FUNCTION wallets_guard_bitcoin_submission()")
        cursor.execute("DROP FUNCTION wallets_guard_bitcoin_input()")
        cursor.execute("DROP FUNCTION wallets_require_bitcoin_inputs()")
        cursor.execute("DROP FUNCTION wallets_guard_bitcoin_identity()")


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0014_native_chain_deployments"),
        ("users", "0021_trigger_types_from_the_column"),
        ("wallets", "0016_wallet_submission"),
    ]

    operations = [
        migrations.CreateModel(
            name="BitcoinSubmission",
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
                    "network",
                    models.CharField(choices=[("test", "test"), ("regtest", "regtest")], editable=False, max_length=10),
                ),
                ("genesis_hash", models.CharField(editable=False, max_length=64)),
                ("sender_address", models.CharField(editable=False, max_length=255)),
                ("tx_hash", models.CharField(editable=False, max_length=64)),
                ("witness_hash", models.CharField(editable=False, max_length=64)),
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
                    "transaction",
                    models.OneToOneField(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bitcoin_submission",
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
                        related_name="bitcoin_submissions",
                        to="wallets.wallet",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BitcoinSubmissionInput",
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
                ("network", models.CharField(editable=False, max_length=10)),
                ("previous_tx_hash", models.CharField(editable=False, max_length=64)),
                ("output_index", models.PositiveBigIntegerField(editable=False)),
                ("satoshis", models.PositiveBigIntegerField(editable=False)),
                ("script", models.BinaryField()),
                ("observed_block_hash", models.CharField(editable=False, max_length=64)),
                (
                    "submission",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inputs",
                        to="wallets.bitcoinsubmission",
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
            ],
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmission",
            constraint=models.UniqueConstraint(fields=("network", "tx_hash"), name="unique_bitcoin_submission_hash"),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(("network__in", ["test", "regtest"])), name="bitcoin_submission_network"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(("tx_hash__regex", "^[0-9a-f]{64}$")), name="bitcoin_submission_hash"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(("witness_hash__regex", "^[0-9a-f]{64}$")), name="bitcoin_submission_witness"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(("genesis_hash__regex", "^[0-9a-f]{64}$")), name="bitcoin_submission_genesis"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmissioninput",
            constraint=models.UniqueConstraint(
                fields=("network", "previous_tx_hash", "output_index"), name="unique_bitcoin_submission_input"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmissioninput",
            constraint=models.CheckConstraint(
                condition=models.Q(("output_index__lt", 4294967296)), name="bitcoin_submission_input_index"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmissioninput",
            constraint=models.CheckConstraint(
                condition=models.Q(("satoshis__lte", 2100000000000000)), name="bitcoin_input_value"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmissioninput",
            constraint=models.CheckConstraint(
                condition=models.Q(("previous_tx_hash__regex", "^[0-9a-f]{64}$")), name="bitcoin_input_hash"
            ),
        ),
        migrations.AddConstraint(
            model_name="bitcoinsubmissioninput",
            constraint=models.CheckConstraint(
                condition=models.Q(("observed_block_hash__regex", "^[0-9a-f]{64}$")), name="bitcoin_input_block"
            ),
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
