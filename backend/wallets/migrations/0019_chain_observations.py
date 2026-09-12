import uuid

import django.db.models.deletion
from django.db import migrations, models

GUARDS = """
CREATE FUNCTION wallets_guard_chain_watch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Chain watches cannot be deleted';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.generation <> 0 OR NEW.last_completed_at IS NOT NULL OR NEW.latest_observation_id IS NOT NULL THEN
            RAISE EXCEPTION 'A chain watch must start without observations';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM transactions t JOIN wallets w ON w.uuid = t.wallet_id
             WHERE t.uuid = NEW.transaction_id AND t.wallet_id = NEW.wallet_id
               AND t.user_account_id = NEW.user_account_id AND w.user_account_id = NEW.user_account_id
               AND t.chain = NEW.chain AND lower(w.chain) = NEW.chain AND t.tx_hash = NEW.tx_hash
               AND NOT t.imported_from_history
               AND (
                   EXISTS (
                       SELECT 1 FROM wallets_walletsubmission s
                        WHERE s.transaction_id = t.uuid AND s.wallet_id = w.uuid
                          AND s.user_account_id = NEW.user_account_id AND s.chain = NEW.chain
                          AND NEW.network = 'evm:' || s.chain_id::text AND s.tx_hash = NEW.tx_hash
                   ) OR EXISTS (
                       SELECT 1 FROM wallets_bitcoinsubmission s
                        WHERE s.transaction_id = t.uuid AND s.wallet_id = w.uuid
                          AND s.user_account_id = NEW.user_account_id AND NEW.chain = 'bitcoin'
                          AND NEW.network = 'bitcoin:' || s.genesis_hash AND s.tx_hash = NEW.tx_hash
                   )
               )
        ) THEN
            RAISE EXCEPTION 'A chain watch must match a durable wallet journal';
        END IF;
        RETURN NEW;
    END IF;
    IF to_jsonb(NEW) - ARRAY['generation', 'target_fingerprint', 'last_started_at', 'last_completed_at', 'latest_observation_id', 'updated_at']
        IS DISTINCT FROM to_jsonb(OLD) - ARRAY['generation', 'target_fingerprint', 'last_started_at', 'last_completed_at', 'latest_observation_id', 'updated_at'] THEN
        RAISE EXCEPTION 'A chain watch cannot change its recorded identity';
    END IF;
    IF NEW.generation = OLD.generation + 1 THEN
        IF NEW.last_started_at IS NULL OR NEW.last_started_at < OLD.last_started_at
            OR NEW.last_completed_at IS DISTINCT FROM OLD.last_completed_at
            OR NEW.latest_observation_id IS DISTINCT FROM OLD.latest_observation_id THEN
            RAISE EXCEPTION 'A new chain claim must retain the previous observation';
        END IF;
    ELSIF NEW.generation = OLD.generation AND NEW.target_fingerprint = OLD.target_fingerprint
        AND NEW.last_started_at IS NOT DISTINCT FROM OLD.last_started_at
        AND NEW.latest_observation_id IS DISTINCT FROM OLD.latest_observation_id
        AND NEW.last_completed_at IS NOT NULL AND NEW.last_completed_at >= NEW.last_started_at
        AND (OLD.last_completed_at IS NULL OR NEW.last_completed_at >= OLD.last_completed_at) THEN
        IF NOT EXISTS (
            SELECT 1 FROM wallets_walletchainobservation o
             WHERE o.uuid = NEW.latest_observation_id AND o.watch_id = NEW.uuid
               AND o.generation = NEW.generation AND o.target_fingerprint = NEW.target_fingerprint
               AND o.started_at = NEW.last_started_at AND o.user_account_id = NEW.user_account_id
        ) THEN
            RAISE EXCEPTION 'The latest chain observation must match its current claim';
        END IF;
    ELSE
        RAISE EXCEPTION 'Chain claims cannot be rewound or completed by another generation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_guard_chain_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Chain observations cannot be rewritten or deleted';
    END IF;
    PERFORM 1 FROM wallets_walletchainwatch w
     WHERE w.uuid = NEW.watch_id AND w.user_account_id = NEW.user_account_id
       AND w.generation = NEW.generation AND w.target_fingerprint = NEW.target_fingerprint
       AND w.last_started_at = NEW.started_at
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A chain observation must match the current watch claim';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER wallets_chain_watch_identity BEFORE INSERT OR UPDATE OR DELETE ON wallets_walletchainwatch
FOR EACH ROW EXECUTE FUNCTION wallets_guard_chain_watch();
CREATE TRIGGER wallets_chain_observation_immutable BEFORE INSERT OR UPDATE OR DELETE ON wallets_walletchainobservation
FOR EACH ROW EXECUTE FUNCTION wallets_guard_chain_observation();
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from shared.db.policy_sql import install_tables

    install_tables(schema_editor, ["wallets_walletchainwatch", "wallets_walletchainobservation"])
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(GUARDS)


def remove_guards(apps, schema_editor):
    for name in ("WalletChainWatch", "WalletChainObservation"):
        if apps.get_model("wallets", name).objects.using(schema_editor.connection.alias).exists():
            raise RuntimeError("Retain wallet chain observations; this migration cannot discard recorded evidence.")
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER wallets_chain_observation_immutable ON wallets_walletchainobservation")
        cursor.execute("DROP TRIGGER wallets_chain_watch_identity ON wallets_walletchainwatch")
        cursor.execute("DROP FUNCTION wallets_guard_chain_observation()")
        cursor.execute("DROP FUNCTION wallets_guard_chain_watch()")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0021_trigger_types_from_the_column"),
        ("wallets", "0018_global_submission_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletChainObservation",
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
                ("generation", models.PositiveBigIntegerField(editable=False)),
                ("target_fingerprint", models.CharField(editable=False, max_length=64)),
                ("started_at", models.DateTimeField(editable=False)),
                (
                    "result",
                    models.CharField(
                        choices=[("unknown", "Unknown"), ("included", "Included"), ("orphaned", "Orphaned")],
                        editable=False,
                        max_length=16,
                    ),
                ),
                (
                    "finality",
                    models.CharField(
                        choices=[("unknown", "Unknown"), ("waiting", "Waiting"), ("satisfied", "Policy satisfied")],
                        editable=False,
                        max_length=16,
                    ),
                ),
                ("reason", models.CharField(blank=True, editable=False, max_length=64)),
                ("policy", models.JSONField(default=dict, editable=False)),
                ("evidence", models.JSONField(default=dict, editable=False)),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="users.useraccount"
                    ),
                ),
            ],
            options={
                "ordering": ["-generation"],
            },
        ),
        migrations.CreateModel(
            name="WalletChainWatch",
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
                ("network", models.CharField(editable=False, max_length=80)),
                ("tx_hash", models.CharField(editable=False, max_length=66)),
                ("generation", models.PositiveBigIntegerField(default=0, editable=False)),
                ("target_fingerprint", models.CharField(blank=True, editable=False, max_length=64)),
                ("last_started_at", models.DateTimeField(db_index=True, editable=False, null=True)),
                ("last_completed_at", models.DateTimeField(editable=False, null=True)),
                (
                    "latest_observation",
                    models.ForeignKey(
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="wallets.walletchainobservation",
                    ),
                ),
                (
                    "transaction",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="chain_watch",
                        to="wallets.transaction",
                    ),
                ),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="users.useraccount"
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="chain_watches", to="wallets.wallet"
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="walletchainobservation",
            name="watch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="observations", to="wallets.walletchainwatch"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainwatch",
            constraint=models.CheckConstraint(
                condition=models.Q(("network__regex", "^(evm:[1-9][0-9]*|bitcoin:[0-9a-f]{64})$")),
                name="wallet_watch_network",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainwatch",
            constraint=models.CheckConstraint(
                condition=models.Q(("tx_hash__regex", "^(0x)?[0-9a-f]{64}$")), name="wallet_watch_hash"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainwatch",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("generation", 0), ("last_started_at__isnull", True), ("target_fingerprint", "")),
                    models.Q(
                        ("generation__gt", 0),
                        ("last_started_at__isnull", False),
                        ("target_fingerprint__regex", "^[0-9a-f]{64}$"),
                    ),
                    _connector="OR",
                ),
                name="wallet_watch_claim",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainobservation",
            constraint=models.UniqueConstraint(fields=("watch", "generation"), name="wallet_observation_generation"),
        ),
        migrations.AddConstraint(
            model_name="walletchainobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("generation__gt", 0)), name="wallet_observation_claim"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("target_fingerprint__regex", "^[0-9a-f]{64}$")), name="wallet_observation_target"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("result__in", ["unknown", "included", "orphaned"])),
                name="wallet_observation_result",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletchainobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("finality", "unknown"),
                    models.Q(("finality__in", ["waiting", "satisfied"]), ("result", "included")),
                    _connector="OR",
                ),
                name="wallet_observation_finality",
            ),
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
