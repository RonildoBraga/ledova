import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from shared.db.policy_sql import install_tables

GUARDS = """
CREATE FUNCTION tokens_order_action_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    issued signing_challenges%ROWTYPE;
    target tokens_transferorder%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Order action identities cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND NEW.status <> 'pending' THEN
        RAISE EXCEPTION 'An order action must start pending' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.uuid, NEW.action_id, NEW.protocol_version, NEW.purpose, NEW.owner_account_id,
               NEW.order_id, NEW.wallet_id, NEW.token_id, NEW.initiated_by_id, NEW.wallet_address,
               NEW.chain_id, NEW.verifying_contract, NEW.token_metadata, NEW.review_values,
               NEW.new_quantity, NEW.new_min_quantity, NEW.new_price_per_share, NEW.created_at)
           IS DISTINCT FROM
           ROW(OLD.uuid, OLD.action_id, OLD.protocol_version, OLD.purpose, OLD.owner_account_id,
               OLD.order_id, OLD.wallet_id, OLD.token_id, OLD.initiated_by_id, OLD.wallet_address,
               OLD.chain_id, OLD.verifying_contract, OLD.token_metadata, OLD.review_values,
               OLD.new_quantity, OLD.new_min_quantity, OLD.new_price_per_share, OLD.created_at) THEN
            RAISE EXCEPTION 'Order action intent cannot be rewritten' USING ERRCODE = '23514';
        END IF;
        IF OLD.status <> 'pending' AND
           ROW(NEW.status, NEW.executed_challenge_id, NEW.executed_by_id, NEW.result,
               NEW.refusal_code, NEW.refusal_detail, NEW.refusal_status, NEW.resolved_at)
           IS DISTINCT FROM
           ROW(OLD.status, OLD.executed_challenge_id, OLD.executed_by_id, OLD.result,
               OLD.refusal_code, OLD.refusal_detail, OLD.refusal_status, OLD.resolved_at) THEN
            RAISE EXCEPTION 'An order action outcome cannot be rewritten' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND OLD.status = 'pending' AND NEW.status <> 'pending') THEN
        SELECT * INTO target FROM tokens_transferorder WHERE uuid = NEW.order_id;
        IF NOT FOUND OR
           ROW(target.owner_account_id, target.wallet_id, target.token_id, lower(target.wallet_address))
           IS DISTINCT FROM
           ROW(NEW.owner_account_id, NEW.wallet_id, NEW.token_id, lower(NEW.wallet_address)) THEN
            RAISE EXCEPTION 'An order action must bind its owned order identity' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'pending' AND NEW.status <> 'pending' THEN
        SELECT * INTO issued FROM signing_challenges WHERE uuid = NEW.executed_challenge_id;
        IF NOT FOUND OR issued.action_id IS DISTINCT FROM NEW.uuid OR issued.consumed_at IS NULL
           OR issued.purpose IS DISTINCT FROM ('order_' || NEW.purpose) THEN
            RAISE EXCEPTION 'An order action outcome requires its spent challenge' USING ERRCODE = '23514';
        END IF;
        IF NEW.status = 'applied' THEN
            IF jsonb_typeof(NEW.result) IS DISTINCT FROM 'object'
               OR NEW.result->>'kind' IS DISTINCT FROM NEW.purpose THEN
                RAISE EXCEPTION 'An applied action requires its original result' USING ERRCODE = '23514';
            END IF;
            IF NEW.purpose = 'cancel' AND (
                target.status <> 'cancelled' OR NEW.result->>'to_status' IS DISTINCT FROM 'cancelled'
                OR COALESCE(NEW.result->>'from_status', '') NOT IN ('open', 'partially_filled')
            ) THEN
                RAISE EXCEPTION 'A cancellation result requires the order transition' USING ERRCODE = '23514';
            END IF;
            IF NEW.purpose = 'modify' AND (
                ROW(target.quantity, target.min_quantity, target.price_per_share)
                IS DISTINCT FROM ROW(NEW.new_quantity, NEW.new_min_quantity, NEW.new_price_per_share)
                OR NEW.result->>'modification_count' IS DISTINCT FROM target.modification_count::text
                OR jsonb_typeof(NEW.result->'changes') IS DISTINCT FROM 'array'
            ) THEN
                RAISE EXCEPTION 'A modification result requires its exact replacement values' USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tokens_order_action_guard BEFORE INSERT OR UPDATE OR DELETE ON tokens_orderactionsubmission
FOR EACH ROW EXECUTE FUNCTION tokens_order_action_guard();

CREATE FUNCTION signing_challenges_bind_action() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    intent tokens_orderactionsubmission%ROWTYPE;
    expected_types jsonb;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.action_id IS DISTINCT FROM OLD.action_id THEN
        RAISE EXCEPTION 'An issued challenge cannot change action linkage' USING ERRCODE = '23514';
    END IF;
    IF NEW.action_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO intent FROM tokens_orderactionsubmission WHERE uuid = NEW.action_id;
    IF NOT FOUND OR NEW.submission_id IS NOT NULL
       OR NEW.purpose IS DISTINCT FROM ('order_' || intent.purpose)
       OR NEW.order_id IS DISTINCT FROM intent.order_id
       OR NEW.wallet_id IS DISTINCT FROM intent.wallet_id
       OR lower(NEW.wallet_address) IS DISTINCT FROM lower(intent.wallet_address)
       OR NEW.chain_id IS DISTINCT FROM intent.chain_id
       OR lower(NEW.verifying_contract) IS DISTINCT FROM lower(intent.verifying_contract)
       OR NEW.payload->'message'->>'actionId' IS DISTINCT FROM intent.action_id::text
       OR NEW.payload->'message'->>'protocolVersion' IS DISTINCT FROM intent.protocol_version::text
       OR NEW.payload->'message'->>'ownerAccountUuid' IS DISTINCT FROM intent.owner_account_id::text
       OR NEW.payload->'message'->>'walletUuid' IS DISTINCT FROM intent.wallet_id::text
       OR NEW.payload->'message'->>'tokenUuid' IS DISTINCT FROM intent.token_id::text
       OR NEW.payload->'message'->>'orderUuid' IS DISTINCT FROM intent.order_id::text
       OR lower(NEW.payload->'message'->>'wallet') IS DISTINCT FROM lower(intent.wallet_address)
       OR NEW.payload->'message'->>'nonce' IS DISTINCT FROM NEW.nonce::text
       OR NEW.payload->'message'->>'deadline' IS DISTINCT FROM floor(extract(epoch FROM NEW.expires_at))::bigint::text
       OR NEW.payload->'domain'->>'name' IS DISTINCT FROM 'Ledova Trading'
       OR NEW.payload->'domain'->>'version' IS DISTINCT FROM '1'
       OR NEW.payload->'domain'->>'chainId' IS DISTINCT FROM intent.chain_id::text
       OR lower(NEW.payload->'domain'->>'verifyingContract') IS DISTINCT FROM lower(intent.verifying_contract) THEN
        RAISE EXCEPTION 'An action challenge must bind its original action identity and domain' USING ERRCODE = '23514';
    END IF;
    IF intent.purpose = 'modify' AND (
        NEW.payload->'message'->>'newQuantity' IS DISTINCT FROM intent.new_quantity::text
        OR NEW.payload->'message'->>'newMinQuantity' IS DISTINCT FROM intent.new_min_quantity::text
        OR NEW.payload->'message'->>'newPricePerShare' IS DISTINCT FROM intent.new_price_per_share::text
    ) THEN
        RAISE EXCEPTION 'A modification challenge must bind all exact replacement values' USING ERRCODE = '23514';
    END IF;
    expected_types = CASE WHEN intent.purpose = 'cancel' THEN '{
    "OrderCancelV1": [
        {
            "name": "actionId",
            "type": "string"
        },
        {
            "name": "protocolVersion",
            "type": "uint256"
        },
        {
            "name": "ownerAccountUuid",
            "type": "string"
        },
        {
            "name": "walletUuid",
            "type": "string"
        },
        {
            "name": "tokenUuid",
            "type": "string"
        },
        {
            "name": "orderUuid",
            "type": "string"
        },
        {
            "name": "wallet",
            "type": "address"
        },
        {
            "name": "nonce",
            "type": "uint256"
        },
        {
            "name": "deadline",
            "type": "uint256"
        }
    ]
}'::jsonb ELSE '{
    "OrderModifyV1": [
        {
            "name": "actionId",
            "type": "string"
        },
        {
            "name": "protocolVersion",
            "type": "uint256"
        },
        {
            "name": "ownerAccountUuid",
            "type": "string"
        },
        {
            "name": "walletUuid",
            "type": "string"
        },
        {
            "name": "tokenUuid",
            "type": "string"
        },
        {
            "name": "orderUuid",
            "type": "string"
        },
        {
            "name": "newQuantity",
            "type": "uint256"
        },
        {
            "name": "newMinQuantity",
            "type": "uint256"
        },
        {
            "name": "newPricePerShare",
            "type": "string"
        },
        {
            "name": "wallet",
            "type": "address"
        },
        {
            "name": "nonce",
            "type": "uint256"
        },
        {
            "name": "deadline",
            "type": "uint256"
        }
    ]
}'::jsonb END;
    IF NEW.payload->'types' IS DISTINCT FROM expected_types THEN
        RAISE EXCEPTION 'An action challenge must sign every declared action field' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER signing_challenges_bind_action BEFORE INSERT OR UPDATE ON signing_challenges
FOR EACH ROW EXECUTE FUNCTION signing_challenges_bind_action();
"""


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    install_tables(schema_editor, ["tokens_orderactionsubmission"])
    schema_editor.execute(GUARDS, params=None)


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER signing_challenges_bind_action ON signing_challenges;"
        "DROP FUNCTION signing_challenges_bind_action();"
        "DROP TRIGGER tokens_order_action_guard ON tokens_orderactionsubmission;"
        "DROP FUNCTION tokens_order_action_guard();"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0037_order_submissions"),
        ("users", "0021_trigger_types_from_the_column"),
        ("wallets", "0014_wallet_network_identity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderActionSubmission",
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
                ("action_id", models.UUIDField(editable=False)),
                ("protocol_version", models.PositiveSmallIntegerField(default=1, editable=False)),
                (
                    "purpose",
                    models.CharField(
                        choices=[("cancel", "Cancel"), ("modify", "Modify")], editable=False, max_length=6
                    ),
                ),
                ("wallet_address", models.CharField(editable=False, max_length=42)),
                ("chain_id", models.PositiveBigIntegerField(editable=False)),
                ("verifying_contract", models.CharField(editable=False, max_length=42)),
                ("token_metadata", models.JSONField(editable=False)),
                ("review_values", models.JSONField(editable=False)),
                ("new_quantity", models.PositiveBigIntegerField(editable=False, null=True)),
                ("new_min_quantity", models.PositiveBigIntegerField(editable=False, null=True)),
                (
                    "new_price_per_share",
                    models.DecimalField(decimal_places=2, editable=False, max_digits=18, null=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("applied", "Applied"), ("refused", "Refused")],
                        default="pending",
                        max_length=7,
                    ),
                ),
                ("result", models.JSONField(blank=True, null=True)),
                ("refusal_code", models.CharField(blank=True, max_length=64)),
                ("refusal_detail", models.CharField(blank=True, max_length=512)),
                ("refusal_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "executed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "executed_challenge",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="action_execution",
                        to="tokens.signingchallenge",
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
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="actions", to="tokens.transferorder"
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
            name="action",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="challenges",
                to="tokens.orderactionsubmission",
            ),
        ),
        migrations.AddConstraint(
            model_name="signingchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("submission__isnull", True), ("action__isnull", True), _connector="OR"),
                name="signing_challenge_one_intent",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderactionsubmission",
            constraint=models.UniqueConstraint(fields=("owner_account", "action_id"), name="order_action_account_key"),
        ),
        migrations.AddConstraint(
            model_name="orderactionsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("chain_id__gt", 0),
                    ("protocol_version", 1),
                    models.Q(
                        models.Q(
                            ("new_min_quantity__isnull", True),
                            ("new_price_per_share__isnull", True),
                            ("new_quantity__isnull", True),
                            ("purpose", "cancel"),
                        ),
                        models.Q(
                            ("new_min_quantity__gte", 0),
                            ("new_min_quantity__isnull", False),
                            ("new_price_per_share__gt", 0),
                            ("new_price_per_share__isnull", False),
                            ("new_price_per_share__lt", Decimal("10000000000000000")),
                            ("new_quantity__gt", 0),
                            ("new_quantity__isnull", False),
                            ("purpose", "modify"),
                        ),
                        _connector="OR",
                    ),
                ),
                name="order_action_valid_intent",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderactionsubmission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("executed_by__isnull", True),
                        ("executed_challenge__isnull", True),
                        ("refusal_code", ""),
                        ("refusal_detail", ""),
                        ("refusal_status__isnull", True),
                        ("resolved_at__isnull", True),
                        ("result__isnull", True),
                        ("status", "pending"),
                    ),
                    models.Q(
                        ("executed_by__isnull", False),
                        ("executed_challenge__isnull", False),
                        ("refusal_code", ""),
                        ("refusal_detail", ""),
                        ("refusal_status__isnull", True),
                        ("resolved_at__isnull", False),
                        ("result__isnull", False),
                        ("status", "applied"),
                    ),
                    models.Q(
                        ("executed_by__isnull", False),
                        ("executed_challenge__isnull", False),
                        ("refusal_status__isnull", False),
                        ("resolved_at__isnull", False),
                        ("result__isnull", True),
                        ("status", "refused"),
                        models.Q(("refusal_detail", ""), _negated=True),
                        models.Q(
                            models.Q(
                                ("purpose", "cancel"),
                                ("refusal_code", "order_cancellation_failed"),
                                ("refusal_status", 400),
                            ),
                            models.Q(
                                ("purpose", "modify"),
                                ("refusal_code", "order_modification_failed"),
                                ("refusal_status", 400),
                            ),
                            models.Q(
                                ("purpose", "modify"),
                                ("refusal_code", "order_modification_conflict"),
                                ("refusal_status", 409),
                            ),
                            _connector="OR",
                        ),
                    ),
                    _connector="OR",
                ),
                name="order_action_outcome_shape",
            ),
        ),
        migrations.RunPython(install_guards, remove_guards),
    ]
