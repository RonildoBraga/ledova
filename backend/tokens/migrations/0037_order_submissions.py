import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from shared.db.policy_sql import install_tables

GUARDS = """
CREATE FUNCTION tokens_order_submission_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    issued signing_challenges%ROWTYPE;
    placed tokens_transferorder%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Order submission identities cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND NEW.status <> 'pending' THEN
        RAISE EXCEPTION 'An order submission must start pending' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.uuid, NEW.submission_id, NEW.owner_account_id, NEW.wallet_id, NEW.token_id,
               NEW.initiated_by_id, NEW.intent_version, NEW.wallet_address, NEW.order_type,
               NEW.quantity, NEW.min_quantity, NEW.price_per_share, NEW.chain_id,
               NEW.verifying_contract, NEW.token_metadata, NEW.created_at)
           IS DISTINCT FROM
           ROW(OLD.uuid, OLD.submission_id, OLD.owner_account_id, OLD.wallet_id, OLD.token_id,
               OLD.initiated_by_id, OLD.intent_version, OLD.wallet_address, OLD.order_type,
               OLD.quantity, OLD.min_quantity, OLD.price_per_share, OLD.chain_id,
               OLD.verifying_contract, OLD.token_metadata, OLD.created_at) THEN
            RAISE EXCEPTION 'Order submission intent cannot be rewritten' USING ERRCODE = '23514';
        END IF;
        IF OLD.status <> 'pending' AND
           ROW(NEW.status, NEW.order_id, NEW.executed_challenge_id, NEW.initial_counter_order_id,
               NEW.initial_swap_id, NEW.refusal_code, NEW.refusal_detail, NEW.resolved_at)
           IS DISTINCT FROM
           ROW(OLD.status, OLD.order_id, OLD.executed_challenge_id, OLD.initial_counter_order_id,
               OLD.initial_swap_id, OLD.refusal_code, OLD.refusal_detail, OLD.resolved_at) THEN
            RAISE EXCEPTION 'A resolved order submission cannot change outcome' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'pending' AND NEW.status <> 'pending' THEN
        SELECT * INTO issued FROM signing_challenges WHERE uuid = NEW.executed_challenge_id;
        IF NOT FOUND OR issued.submission_id IS DISTINCT FROM NEW.uuid
           OR issued.consumed_at IS NULL OR issued.purpose <> 'order_create' THEN
            RAISE EXCEPTION 'An order submission outcome requires its spent challenge' USING ERRCODE = '23514';
        END IF;
        IF NEW.status = 'created' THEN
            SELECT * INTO placed FROM tokens_transferorder WHERE uuid = NEW.order_id;
            IF NOT FOUND OR
               ROW(placed.owner_account_id, placed.wallet_id, placed.token_id, placed.wallet_address,
                   placed.order_type, placed.quantity, placed.min_quantity, placed.price_per_share)
               IS DISTINCT FROM
               ROW(NEW.owner_account_id, NEW.wallet_id, NEW.token_id, NEW.wallet_address,
                   NEW.order_type, NEW.quantity, NEW.min_quantity, NEW.price_per_share) THEN
                RAISE EXCEPTION 'An order submission must resolve to its original order intent'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.initial_swap_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM tokens_swaporder
                 WHERE uuid = NEW.initial_swap_id
                   AND ((sell_order_id = NEW.order_id AND buy_order_id = NEW.initial_counter_order_id)
                     OR (buy_order_id = NEW.order_id AND sell_order_id = NEW.initial_counter_order_id))
            ) THEN
                RAISE EXCEPTION 'An order submission match must name its original order pair'
                    USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tokens_order_submission_guard BEFORE INSERT OR UPDATE OR DELETE ON tokens_ordersubmission
FOR EACH ROW EXECUTE FUNCTION tokens_order_submission_guard();

CREATE FUNCTION signing_challenges_bind_submission() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    intent tokens_ordersubmission%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.submission_id IS DISTINCT FROM OLD.submission_id THEN
        RAISE EXCEPTION 'An issued challenge cannot change submission linkage' USING ERRCODE = '23514';
    END IF;
    IF NEW.submission_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO intent FROM tokens_ordersubmission WHERE uuid = NEW.submission_id;
    IF NOT FOUND OR NEW.purpose <> 'order_create' OR NEW.order_id IS NOT NULL
       OR NEW.wallet_id IS DISTINCT FROM intent.wallet_id
       OR NEW.wallet_address IS DISTINCT FROM intent.wallet_address
       OR NEW.chain_id IS DISTINCT FROM intent.chain_id
       OR lower(NEW.verifying_contract) IS DISTINCT FROM lower(intent.verifying_contract)
       OR NEW.payload->'message'->>'submissionId' IS DISTINCT FROM intent.submission_id::text
       OR NEW.payload->'message'->>'ownerAccountUuid' IS DISTINCT FROM intent.owner_account_id::text
       OR NEW.payload->'message'->>'walletUuid' IS DISTINCT FROM intent.wallet_id::text
       OR NEW.payload->'message'->>'tokenUuid' IS DISTINCT FROM intent.token_id::text
       OR NEW.payload->'message'->>'orderType' IS DISTINCT FROM intent.order_type
       OR NEW.payload->'message'->>'quantity' IS DISTINCT FROM intent.quantity::text
       OR NEW.payload->'message'->>'minQuantity' IS DISTINCT FROM intent.min_quantity::text
       OR NEW.payload->'message'->>'pricePerShare' IS DISTINCT FROM intent.price_per_share::text
       OR lower(NEW.payload->'message'->>'wallet') IS DISTINCT FROM lower(intent.wallet_address)
       OR NEW.payload->'domain'->>'chainId' IS DISTINCT FROM intent.chain_id::text
       OR lower(NEW.payload->'domain'->>'verifyingContract') IS DISTINCT FROM lower(intent.verifying_contract) THEN
        RAISE EXCEPTION 'A create challenge must bind its original submission intent' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER signing_challenges_bind_submission BEFORE INSERT OR UPDATE ON signing_challenges
FOR EACH ROW EXECUTE FUNCTION signing_challenges_bind_submission();
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    install_tables(schema_editor, ["tokens_ordersubmission"])
    schema_editor.execute(GUARDS, params=None)


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER signing_challenges_bind_submission ON signing_challenges;"
        "DROP FUNCTION signing_challenges_bind_submission();"
        "DROP TRIGGER tokens_order_submission_guard ON tokens_ordersubmission;"
        "DROP FUNCTION tokens_order_submission_guard();"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0036_swap_expiry_eligibility"),
        ("users", "0021_trigger_types_from_the_column"),
        ("wallets", "0014_wallet_network_identity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderSubmission",
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
                ("submission_id", models.UUIDField(editable=False)),
                ("intent_version", models.PositiveSmallIntegerField(default=1, editable=False)),
                ("wallet_address", models.CharField(editable=False, max_length=42)),
                (
                    "order_type",
                    models.CharField(choices=[("buy", "Buy"), ("sell", "Sell")], editable=False, max_length=10),
                ),
                ("quantity", models.PositiveBigIntegerField(editable=False)),
                ("min_quantity", models.PositiveBigIntegerField(default=0, editable=False)),
                ("price_per_share", models.DecimalField(decimal_places=2, editable=False, max_digits=18)),
                ("chain_id", models.PositiveBigIntegerField(editable=False)),
                ("verifying_contract", models.CharField(editable=False, max_length=42)),
                ("token_metadata", models.JSONField(editable=False)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("created", "Created"), ("refused", "Refused")],
                        default="pending",
                        max_length=7,
                    ),
                ),
                ("refusal_code", models.CharField(blank=True, max_length=32)),
                ("refusal_detail", models.CharField(blank=True, max_length=200)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "executed_challenge",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="execution",
                        to="tokens.signingchallenge",
                    ),
                ),
                (
                    "initial_counter_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="tokens.transferorder",
                    ),
                ),
                (
                    "initial_swap",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="tokens.swaporder",
                    ),
                ),
                (
                    "initiated_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "order",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submission",
                        to="tokens.transferorder",
                    ),
                ),
                (
                    "owner_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="users.useraccount"
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tokens.sharetoken"
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="wallets.wallet"
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="signingchallenge",
            name="submission",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="challenges",
                to="tokens.ordersubmission",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordersubmission",
            constraint=models.UniqueConstraint(
                fields=("owner_account", "submission_id"), name="order_submission_account_key"
            ),
        ),
        migrations.AddConstraint(
            model_name="ordersubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("chain_id__gt", 0),
                    ("intent_version", 1),
                    ("quantity__gt", 0),
                    ("min_quantity__gte", 0),
                    ("min_quantity__lte", models.F("quantity")),
                    ("price_per_share__gt", 0),
                    ("price_per_share__lt", Decimal("10000000000000000")),
                    ("order_type__in", ["buy", "sell"]),
                ),
                name="order_submission_valid_terms",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordersubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("executed_challenge__isnull", True),
                        ("initial_counter_order__isnull", True),
                        ("initial_swap__isnull", True),
                        ("order__isnull", True),
                        ("refusal_code", ""),
                        ("refusal_detail", ""),
                        ("resolved_at__isnull", True),
                        ("status", "pending"),
                    ),
                    models.Q(
                        ("executed_challenge__isnull", False),
                        ("order__isnull", False),
                        ("refusal_code", ""),
                        ("refusal_detail", ""),
                        ("resolved_at__isnull", False),
                        ("status", "created"),
                    ),
                    models.Q(
                        ("executed_challenge__isnull", False),
                        ("initial_counter_order__isnull", True),
                        ("initial_swap__isnull", True),
                        ("order__isnull", True),
                        ("refusal_code__in", ["not_whitelisted", "insufficient_balance"]),
                        ("resolved_at__isnull", False),
                        ("status", "refused"),
                        models.Q(("refusal_detail", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="order_submission_outcome_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="ordersubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("initial_counter_order__isnull", True), ("initial_swap__isnull", True)),
                    models.Q(("initial_counter_order__isnull", False), ("initial_swap__isnull", False)),
                    _connector="OR",
                ),
                name="order_submission_match_pair",
            ),
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
