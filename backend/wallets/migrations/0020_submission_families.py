import uuid
from decimal import Decimal, localcontext

import django.db.models.deletion
from django.db import migrations, models

GUARDS = """
CREATE FUNCTION wallets_guard_submission_family() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Submission families cannot be deleted';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF to_jsonb(NEW) - ARRAY['selected_id', 'winner_id', 'winner_observation_id', 'generation', 'native_exposure', 'token_exposure', 'updated_at']
            IS DISTINCT FROM to_jsonb(OLD) - ARRAY['selected_id', 'winner_id', 'winner_observation_id', 'generation', 'native_exposure', 'token_exposure', 'updated_at'] THEN
            RAISE EXCEPTION 'A submission family cannot change its original identity';
        END IF;
        IF NEW.generation <> OLD.generation + 1 OR NEW.native_exposure < OLD.native_exposure OR NEW.token_exposure < OLD.token_exposure THEN
            RAISE EXCEPTION 'Family generations and exposure cannot be rewound';
        END IF;
        IF ROW(NEW.winner_id, NEW.winner_observation_id) IS DISTINCT FROM ROW(OLD.winner_id, OLD.winner_observation_id) THEN
            IF NOT EXISTS (
                SELECT 1 FROM wallets_walletchainobservation o
                JOIN wallets_walletchainwatch w ON w.uuid = o.watch_id
                JOIN wallets_walletsubmission s ON s.transaction_id = w.transaction_id
                WHERE o.uuid = NEW.winner_observation_id AND s.family_id = NEW.uuid
                  AND o.family_generation = OLD.generation AND o.generation = w.generation
                  AND w.latest_observation_id = o.uuid AND o.user_account_id = NEW.user_account_id
                  AND (
                      (OLD.winner_id IS NULL AND s.uuid = NEW.winner_id AND o.result = 'included')
                      OR (OLD.winner_id IS NOT NULL AND NEW.winner_id IS NULL AND s.uuid = OLD.winner_id
                          AND o.result = 'orphaned' AND o.evidence->>'previous_orphaned' = 'true'
                          AND EXISTS (SELECT 1 FROM wallets_walletchainobservation previous
                                      WHERE previous.uuid = OLD.winner_observation_id
                                        AND o.evidence->'previous_block' = jsonb_build_object(
                                            'hash', previous.evidence->'receipt'->'hash',
                                            'height', previous.evidence->'receipt'->'height')))
                  )
            ) THEN
                RAISE EXCEPTION 'A family winner transition requires current attributable chain evidence';
            END IF;
        END IF;
    ELSIF NOT EXISTS (SELECT 1 FROM wallets w WHERE w.uuid = NEW.wallet_id AND w.user_account_id = NEW.user_account_id
                       AND lower(w.address) = NEW.sender_address AND lower(w.chain) = NEW.chain) THEN
        RAISE EXCEPTION 'A submission family must match its wallet';
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_check_submission_family() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    f wallets_walletsubmissionfamily%ROWTYPE;
BEGIN
    IF TG_TABLE_NAME = 'wallets_walletsubmission' THEN
        SELECT * INTO f FROM wallets_walletsubmissionfamily WHERE uuid = NEW.family_id;
    ELSE
        SELECT * INTO f FROM wallets_walletsubmissionfamily WHERE uuid = NEW.uuid;
    END IF;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM wallets_walletsubmission s WHERE s.uuid = f.selected_id AND s.family_id = f.uuid)
       OR NOT EXISTS (SELECT 1 FROM wallets_walletsubmission s WHERE s.family_id = f.uuid AND s.kind = 'original'
                        AND s.tx_hash = f.original_tx_hash AND s.intent = f.original_intent
                        AND s.asset_id = f.asset_id AND s.deployment_id IS NOT DISTINCT FROM f.deployment_id)
       OR f.native_exposure IS DISTINCT FROM (SELECT max((s.intent->>'value')::numeric / 1000000000000000000 + (s.intent->>'maximum_fee')::numeric)
                                               FROM wallets_walletsubmission s WHERE s.family_id = f.uuid)
       OR f.token_exposure IS DISTINCT FROM (CASE WHEN f.deployment_id IS NULL THEN 0 ELSE (f.original_intent->>'amount')::numeric END) THEN
        RAISE EXCEPTION 'A family must retain its original intent, selected member and maximum exposure';
    END IF;
    IF f.winner_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM wallets_walletsubmission s
        JOIN wallets_walletchainwatch w ON w.transaction_id = s.transaction_id
        JOIN wallets_walletchainobservation o ON o.watch_id = w.uuid
        WHERE s.uuid = f.winner_id AND s.family_id = f.uuid AND o.uuid = f.winner_observation_id
          AND o.result = 'included' AND o.user_account_id = f.user_account_id
    ) THEN
        RAISE EXCEPTION 'A family winner must have its own included observation';
    END IF;
    RETURN NULL;
END;
$$;
CREATE FUNCTION wallets_guard_submission_member() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    f wallets_walletsubmissionfamily%ROWTYPE;
    p wallets_walletsubmission%ROWTYPE;
    price numeric;
    tip numeric;
    parent_price numeric;
    parent_tip numeric;
BEGIN
    SELECT * INTO f FROM wallets_walletsubmissionfamily WHERE uuid = NEW.family_id;
    IF NOT FOUND OR ROW(f.wallet_id, f.user_account_id, f.chain, f.chain_id, f.sender_address, f.nonce)
        IS DISTINCT FROM ROW(NEW.wallet_id, NEW.user_account_id, NEW.chain, NEW.chain_id, NEW.sender_address, NEW.nonce) THEN
        RAISE EXCEPTION 'A signed attempt must match its family';
    END IF;
    price := CASE WHEN NEW.intent->>'envelope_type' = '2' THEN (NEW.intent->>'max_fee_per_gas')::numeric ELSE (NEW.intent->>'gas_price')::numeric END;
    tip := CASE WHEN NEW.intent->>'envelope_type' = '2' THEN (NEW.intent->>'max_priority_fee_per_gas')::numeric ELSE price END;
    IF price IS NULL OR price <= 0 OR tip IS NULL OR tip < 0 OR tip > price
       OR (NEW.intent->>'gas_limit')::numeric IS NULL OR (NEW.intent->>'gas_limit')::numeric <= 0
       OR (NEW.intent->>'maximum_fee')::numeric IS DISTINCT FROM (NEW.intent->>'gas_limit')::numeric * price / 1000000000000000000 THEN
        RAISE EXCEPTION 'A signed attempt must retain its maximum execution fee';
    END IF;
    IF NEW.kind = 'original' THEN
        IF f.original_tx_hash <> NEW.tx_hash OR f.selected_id IS NOT NULL THEN
            RAISE EXCEPTION 'A family has one original signed attempt';
        END IF;
        RETURN NEW;
    END IF;
    SELECT * INTO p FROM wallets_walletsubmission WHERE uuid = NEW.parent_id AND family_id = f.uuid;
    IF NOT FOUND OR NEW.parent_id IS DISTINCT FROM f.selected_id OR f.winner_id IS NOT NULL THEN
        RAISE EXCEPTION 'A replacement must name the current unresolved parent';
    END IF;
    parent_price := CASE WHEN p.intent->>'envelope_type' = '2' THEN (p.intent->>'max_fee_per_gas')::numeric ELSE (p.intent->>'gas_price')::numeric END;
    parent_tip := CASE WHEN p.intent->>'envelope_type' = '2' THEN (p.intent->>'max_priority_fee_per_gas')::numeric ELSE parent_price END;
    IF price <= parent_price OR tip < parent_tip THEN
        RAISE EXCEPTION 'A replacement must advance its signed fee terms';
    END IF;
    IF NEW.kind = 'speed_up' THEN
        IF ROW(NEW.asset_id, NEW.deployment_id, lower(NEW.intent->>'envelope_to'), (NEW.intent->>'value')::numeric,
               lower(NEW.intent->>'to_address'), (NEW.intent->>'amount')::numeric, (NEW.intent->>'raw_amount')::numeric,
               lower(NEW.intent->>'token_contract'), (NEW.intent->>'asset_decimals')::integer)
           IS DISTINCT FROM
           ROW(f.asset_id, f.deployment_id, lower(f.original_intent->>'envelope_to'), (f.original_intent->>'value')::numeric,
               lower(f.original_intent->>'to_address'), (f.original_intent->>'amount')::numeric, (f.original_intent->>'raw_amount')::numeric,
               lower(f.original_intent->>'token_contract'), (f.original_intent->>'asset_decimals')::integer) THEN
            RAISE EXCEPTION 'A speed-up must preserve the original economic intent';
        END IF;
    ELSIF NEW.kind = 'cancellation' THEN
        IF NEW.deployment_id IS NOT NULL OR NEW.intent->>'token_contract' IS NOT NULL
           OR (NEW.intent->>'value')::numeric IS DISTINCT FROM 0 OR (NEW.intent->>'amount')::numeric IS DISTINCT FROM 0
           OR (NEW.intent->>'raw_amount')::numeric IS DISTINCT FROM 0 OR (NEW.intent->>'asset_decimals')::integer IS DISTINCT FROM 18
           OR lower(NEW.intent->>'envelope_to') IS DISTINCT FROM f.sender_address
           OR lower(NEW.intent->>'to_address') IS DISTINCT FROM f.sender_address
           OR NOT EXISTS (SELECT 1 FROM assets_asset a JOIN asset_chain_deployments d ON d.asset_id = a.uuid
                          WHERE a.uuid = NEW.asset_id AND a.asset_type = 'native_crypto'
                            AND d.chain = NEW.chain AND d.contract_address IS NULL AND d.decimals = 18) THEN
            RAISE EXCEPTION 'A cancellation must be a zero-value native call to this sender';
        END IF;
    ELSE
        RAISE EXCEPTION 'Unknown family attempt kind';
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_guard_observed_family_claim() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    generation bigint;
BEGIN
    SELECT f.generation INTO generation FROM wallets_walletchainwatch w
    JOIN wallets_walletsubmission s ON s.transaction_id = w.transaction_id
    JOIN wallets_walletsubmissionfamily f ON f.uuid = s.family_id WHERE w.uuid = NEW.watch_id;
    IF NEW.family_generation IS DISTINCT FROM generation THEN
        RAISE EXCEPTION 'A chain observation must retain its current family generation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_guard_balance_projection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Balance projections cannot be rewritten or deleted';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM wallets w WHERE w.uuid = NEW.wallet_id AND w.user_account_id = NEW.user_account_id)
       OR jsonb_typeof(NEW.observation) <> 'object'
       OR coalesce(NEW.observation->>'block_hash', '') !~ '^0x[0-9a-f]{64}$'
       OR coalesce(NEW.observation->>'block_number', '') !~ '^[0-9]+$'
       OR coalesce(NEW.observation->>'nonce', '') !~ '^[0-9]+$'
       OR coalesce(NEW.observation->>'balance_wei', '') !~ '^[0-9]+$'
       OR jsonb_typeof(NEW.reservations) <> 'array' OR jsonb_typeof(NEW.quantities) <> 'object' THEN
        RAISE EXCEPTION 'A projection must preserve a bounded wallet observation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE FUNCTION wallets_guard_holding_projection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.balance_projection_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM wallets_walletbalanceprojection p WHERE p.uuid = NEW.balance_projection_id
          AND p.wallet_id = NEW.wallet_id AND p.quantities ? NEW.asset_id::text
    ) THEN
        RAISE EXCEPTION 'A holding projection must belong to this wallet and asset';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER wallets_observed_family_claim BEFORE INSERT ON wallets_walletchainobservation
FOR EACH ROW EXECUTE FUNCTION wallets_guard_observed_family_claim();
CREATE TRIGGER wallets_submission_family_identity BEFORE INSERT OR UPDATE OR DELETE ON wallets_walletsubmissionfamily
FOR EACH ROW EXECUTE FUNCTION wallets_guard_submission_family();
CREATE TRIGGER wallets_submission_member_identity BEFORE INSERT ON wallets_walletsubmission
FOR EACH ROW EXECUTE FUNCTION wallets_guard_submission_member();
CREATE CONSTRAINT TRIGGER wallets_submission_family_complete AFTER INSERT OR UPDATE ON wallets_walletsubmissionfamily
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION wallets_check_submission_family();
CREATE CONSTRAINT TRIGGER wallets_submission_member_complete AFTER INSERT ON wallets_walletsubmission
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION wallets_check_submission_family();
CREATE TRIGGER wallets_balance_projection_immutable BEFORE INSERT OR UPDATE OR DELETE ON wallets_walletbalanceprojection
FOR EACH ROW EXECUTE FUNCTION wallets_guard_balance_projection();
CREATE TRIGGER wallets_holding_projection_identity BEFORE INSERT OR UPDATE ON holdings
FOR EACH ROW EXECUTE FUNCTION wallets_guard_holding_projection();
"""


def backfill_families(apps, schema_editor):
    alias = schema_editor.connection.alias
    submissions = apps.get_model("wallets", "WalletSubmission").objects.using(alias)
    families = apps.get_model("wallets", "WalletSubmissionFamily").objects.using(alias)
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER wallets_submission_immutable ON wallets_walletsubmission")
    with localcontext() as context:
        context.prec = 90
        for submission in submissions.order_by("pk").iterator():
            intent = submission.intent
            family = families.create(
                wallet_id=submission.wallet_id,
                user_account_id=submission.user_account_id,
                chain=submission.chain,
                chain_id=submission.chain_id,
                sender_address=submission.sender_address,
                nonce=submission.nonce,
                asset_id=submission.asset_id,
                deployment_id=submission.deployment_id,
                original_tx_hash=submission.tx_hash,
                original_intent=intent,
                selected_id=submission.pk,
                generation=1,
                native_exposure=Decimal(intent["value"]).scaleb(-18) + Decimal(intent["maximum_fee"]),
                token_exposure=Decimal(intent["amount"]) if submission.deployment_id else Decimal("0"),
            )
            submissions.filter(pk=submission.pk).update(family_id=family.pk)
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE TRIGGER wallets_submission_immutable BEFORE INSERT OR UPDATE OR DELETE ON wallets_walletsubmission FOR EACH ROW EXECUTE FUNCTION wallets_guard_submission()"
        )


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    from shared.db.policy_sql import install_tables

    install_tables(schema_editor, ["wallets_walletsubmissionfamily", "wallets_walletbalanceprojection"])
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(GUARDS)


def remove_guards(apps, schema_editor):
    for name in ("WalletSubmissionFamily", "WalletBalanceProjection"):
        if apps.get_model("wallets", name).objects.using(schema_editor.connection.alias).exists():
            raise RuntimeError(
                "Retain wallet families and balance evidence; this migration cannot discard recorded state."
            )
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("wallets_walletsubmissionfamily", "wallets_walletbalanceprojection"):
        for suffix in ("read", "insert", "update", "delete"):
            schema_editor.execute(f"DROP POLICY {table}_{suffix} ON {table}")
    for table, trigger in (
        ("wallets_walletsubmissionfamily", "wallets_submission_family_identity"),
        ("wallets_walletsubmissionfamily", "wallets_submission_family_complete"),
        ("wallets_walletsubmission", "wallets_submission_member_identity"),
        ("wallets_walletsubmission", "wallets_submission_member_complete"),
        ("wallets_walletbalanceprojection", "wallets_balance_projection_immutable"),
        ("holdings", "wallets_holding_projection_identity"),
        ("wallets_walletchainobservation", "wallets_observed_family_claim"),
    ):
        schema_editor.execute(f"DROP TRIGGER {trigger} ON {table}")
    for function in (
        "wallets_guard_submission_family",
        "wallets_check_submission_family",
        "wallets_guard_submission_member",
        "wallets_guard_balance_projection",
        "wallets_guard_holding_projection",
        "wallets_guard_observed_family_claim",
    ):
        schema_editor.execute(f"DROP FUNCTION {function}()")


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0014_native_chain_deployments"),
        ("users", "0021_trigger_types_from_the_column"),
        ("wallets", "0019_chain_observations"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletBalanceProjection",
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
                ("observation", models.JSONField(editable=False)),
                ("reservations", models.JSONField(editable=False)),
                ("quantities", models.JSONField(editable=False)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="WalletSubmissionFamily",
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
                ("original_tx_hash", models.CharField(editable=False, max_length=66)),
                ("original_intent", models.JSONField(editable=False)),
                ("generation", models.PositiveBigIntegerField(default=0, editable=False)),
                ("native_exposure", models.DecimalField(decimal_places=18, max_digits=40)),
                ("token_exposure", models.DecimalField(decimal_places=18, default=0, max_digits=40)),
            ],
        ),
        migrations.AddField(
            model_name="walletsubmission",
            name="kind",
            field=models.CharField(default="original", editable=False, max_length=16),
        ),
        migrations.AddField(
            model_name="walletsubmission",
            name="parent",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="wallets.walletsubmission",
            ),
        ),
        migrations.AddField(
            model_name="walletbalanceprojection",
            name="user_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="+", to="users.useraccount"
            ),
        ),
        migrations.AddField(
            model_name="walletbalanceprojection",
            name="wallet",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="balance_projections", to="wallets.wallet"
            ),
        ),
        migrations.AddField(
            model_name="holding",
            name="balance_projection",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="wallets.walletbalanceprojection",
            ),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="asset",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="assets.asset"),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="deployment",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="assets.assetchaindeployment",
            ),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="selected",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="wallets.walletsubmission"
            ),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="user_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="+", to="users.useraccount"
            ),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="wallet",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="submission_families", to="wallets.wallet"
            ),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="winner",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="wallets.walletsubmission"
            ),
        ),
        migrations.AddField(
            model_name="walletsubmissionfamily",
            name="winner_observation",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="wallets.walletchainobservation",
            ),
        ),
        migrations.AddField(
            model_name="walletsubmission",
            name="family",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempts",
                to="wallets.walletsubmissionfamily",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(("kind__in", ["original", "speed_up", "cancellation"])),
                name="wallet_submission_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("kind", "original"), ("parent__isnull", True)),
                    models.Q(("kind__in", ["speed_up", "cancellation"]), ("parent__isnull", False)),
                    _connector="OR",
                ),
                name="wallet_submission_parent",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmissionfamily",
            constraint=models.UniqueConstraint(
                fields=("wallet", "chain_id", "nonce"), name="unique_wallet_family_nonce"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmissionfamily",
            constraint=models.UniqueConstraint(
                fields=("chain_id", "sender_address", "nonce"), name="unique_family_sender_nonce"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmissionfamily",
            constraint=models.CheckConstraint(condition=models.Q(("chain_id__gt", 0)), name="wallet_family_chain_id"),
        ),
        migrations.AddConstraint(
            model_name="walletsubmissionfamily",
            constraint=models.CheckConstraint(
                condition=models.Q(("native_exposure__gte", 0), ("token_exposure__gte", 0)),
                name="wallet_family_exposure",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmissionfamily",
            constraint=models.CheckConstraint(
                condition=models.Q(("sender_address__regex", "^0x[0-9a-f]{40}$")), name="wallet_family_sender"
            ),
        ),
        migrations.AddConstraint(
            model_name="walletsubmissionfamily",
            constraint=models.CheckConstraint(
                condition=models.Q(("original_tx_hash__regex", "^0x[0-9a-f]{64}$")), name="wallet_family_hash"
            ),
        ),
        migrations.AddField(
            model_name="walletchainobservation",
            name="family_generation",
            field=models.PositiveBigIntegerField(null=True, editable=False),
        ),
        migrations.RunPython(backfill_families, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="walletsubmission",
            name="family",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attempts",
                to="wallets.walletsubmissionfamily",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="walletsubmission",
            name="unique_wallet_submission_nonce",
        ),
        migrations.RemoveConstraint(
            model_name="walletsubmission",
            name="unique_submission_sender_nonce",
        ),
        migrations.AddConstraint(
            model_name="walletsubmission",
            constraint=models.UniqueConstraint(
                fields=["family"], condition=models.Q(kind="original"), name="unique_family_original"
            ),
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
