from decimal import Decimal

from django.db import migrations, models


def refuse_invalid_trading_rows(apps, schema_editor):
    violations = []
    for operation in Migration.operations:
        if not isinstance(operation, migrations.AddConstraint):
            continue
        model = apps.get_model("tokens", operation.model_name)
        invalid = list(
            model._base_manager.using(schema_editor.connection.alias)
            .exclude(operation.constraint.condition)
            .order_by("pk")
            .values_list("pk", flat=True)[:20]
        )
        if invalid:
            violations.append(operation.constraint.name + ": " + ", ".join(str(pk) for pk in invalid))
    if violations:
        raise RuntimeError(
            "Trading state invariants cannot be installed. First 20 invalid identifiers per rule:\n"
            + "\n".join(violations)
            + "\nNo rows have been changed. Resolve these records explicitly before retrying; "
            "do not rewrite signed intent, clear spent challenges, or release unresolved reservations."
        )


def protect_issued_challenges(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION signing_challenges_preserve_issued_intent() RETURNS trigger AS $$
        BEGIN
            IF ROW(NEW.uuid, NEW.purpose, NEW.wallet_id, NEW.wallet_address, NEW.order_id,
                   NEW.chain_id, NEW.verifying_contract, NEW.nonce, NEW.digest, NEW.payload,
                   NEW.expires_at, NEW.created_at)
               IS DISTINCT FROM
               ROW(OLD.uuid, OLD.purpose, OLD.wallet_id, OLD.wallet_address, OLD.order_id,
                   OLD.chain_id, OLD.verifying_contract, OLD.nonce, OLD.digest, OLD.payload,
                   OLD.expires_at, OLD.created_at) THEN
                RAISE EXCEPTION 'An issued signing challenge cannot change its intent'
                    USING ERRCODE = '23514';
            END IF;
            IF OLD.consumed_at IS NOT NULL AND
               ROW(NEW.consumed_at, NEW.consumed_signature)
               IS DISTINCT FROM ROW(OLD.consumed_at, OLD.consumed_signature) THEN
                RAISE EXCEPTION 'A consumed signing challenge cannot be reset or spent differently'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER signing_challenges_preserve_issued_intent
        BEFORE UPDATE ON signing_challenges
        FOR EACH ROW EXECUTE FUNCTION signing_challenges_preserve_issued_intent();
        """)


def unprotect_issued_challenges(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP TRIGGER signing_challenges_preserve_issued_intent ON signing_challenges;"
            "DROP FUNCTION signing_challenges_preserve_issued_intent();"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0014_native_chain_deployments"),
        ("blockchain", "0004_durable_outgoing"),
        ("tokens", "0034_shareissuance_mint_journal"),
        ("users", "0021_trigger_types_from_the_column"),
        ("wallets", "0014_wallet_network_identity"),
    ]

    operations = [
        migrations.RunPython(refuse_invalid_trading_rows, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="signingchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("consumed_at__isnull", True), ("consumed_signature", "")),
                    models.Q(("consumed_at__isnull", False), models.Q(("consumed_signature", ""), _negated=True)),
                    _connector="OR",
                ),
                name="signing_challenge_complete_spend",
            ),
        ),
        migrations.AddConstraint(
            model_name="swaporder",
            constraint=models.CheckConstraint(
                condition=models.Q(("share_amount__gt", 0)), name="swap_order_positive_shares"
            ),
        ),
        migrations.AddConstraint(
            model_name="swaporder",
            constraint=models.CheckConstraint(
                condition=models.Q(("payment_amount__gt", 0)), name="swap_order_positive_payment"
            ),
        ),
        migrations.AddConstraint(
            model_name="swaporder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
                            "created",
                            "seller_signed",
                            "buyer_signed",
                            "ready",
                            "executing",
                            "completed",
                            "failed",
                            "expired",
                        ],
                    )
                ),
                name="swap_order_known_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)), name="transfer_order_positive_quantity"
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("price_per_share__gt", 0), ("price_per_share__lt", Decimal("10000000000000000"))),
                name="transfer_order_positive_price",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("filled_quantity__gte", 0), ("filled_quantity__lte", models.F("quantity"))),
                name="transfer_order_filled_bounds",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("min_quantity__gte", 0), ("min_quantity__lte", models.F("quantity"))),
                name="transfer_order_minimum_bounds",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
                            "open",
                            "partially_filled",
                            "matched",
                            "pending_signature",
                            "executing",
                            "completed",
                            "cancelled",
                            "expired",
                            "failed",
                        ],
                    )
                ),
                name="transfer_order_known_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferorder",
            constraint=models.CheckConstraint(
                condition=models.Q(("order_type__in", ["buy", "sell"])), name="transfer_order_known_type"
            ),
        ),
        migrations.RunPython(protect_issued_challenges, unprotect_issued_challenges),
    ]
