from importlib import import_module

from django.db import migrations

PARENT_GUARD = """
CREATE FUNCTION tokens_order_owner_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.uuid, NEW.owner_account_id, NEW.wallet_id, lower(NEW.wallet_address))
       IS DISTINCT FROM ROW(OLD.uuid, OLD.owner_account_id, OLD.wallet_id, lower(OLD.wallet_address)) THEN
        RAISE EXCEPTION 'An order owner identity cannot change' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tokens_order_owner_identity_guard BEFORE UPDATE ON tokens_transferorder
FOR EACH ROW EXECUTE FUNCTION tokens_order_owner_identity_guard();
"""

CURRENT_PARTY = """
CREATE FUNCTION tokens_swap_has_current_party(candidate tokens_swaporder)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '') IS NOT NULL AND EXISTS (
        SELECT 1 FROM tokens_transferorder owned
        JOIN wallets held ON held.uuid = owned.wallet_id
        WHERE owned.owner_account_id IN (SELECT app_member_account_ids())
          AND held.user_account_id = owned.owner_account_id
          AND lower(held.address) = lower(owned.wallet_address)
          AND held.verification_status = 'VERIFIED'
          AND held.chain IN ('ethereum', 'base')
          AND owned.token_id = candidate.share_token_id
          AND (
              (owned.uuid = candidate.sell_order_id
               AND owned.wallet_id = candidate.seller_wallet_id
               AND lower(held.address) = lower(candidate.seller_address)
               AND candidate.settlement_context->'seller'->>'order_uuid' = owned.uuid::text
               AND candidate.settlement_context->'seller'->>'owner_account_uuid' = owned.owner_account_id::text
               AND candidate.settlement_context->'seller'->>'wallet_uuid' = owned.wallet_id::text
               AND lower(candidate.settlement_context->'seller'->>'address') = lower(held.address)
               AND (candidate.settlement_context->'seller'->>'payment_asset_uuid')
                   IS NOT DISTINCT FROM owned.payment_asset_id::text)
              OR
              (owned.uuid = candidate.buy_order_id
               AND owned.wallet_id = candidate.buyer_wallet_id
               AND lower(held.address) = lower(candidate.buyer_address)
               AND candidate.settlement_context->'buyer'->>'order_uuid' = owned.uuid::text
               AND candidate.settlement_context->'buyer'->>'owner_account_uuid' = owned.owner_account_id::text
               AND candidate.settlement_context->'buyer'->>'wallet_uuid' = owned.wallet_id::text
               AND lower(candidate.settlement_context->'buyer'->>'address') = lower(held.address)
               AND (candidate.settlement_context->'buyer'->>'payment_asset_uuid')
                   IS NOT DISTINCT FROM owned.payment_asset_id::text)
          )
    );
$$;
"""

PARTICIPANT_UPDATE = """
    IF TG_OP = 'UPDATE' AND OLD.settlement_protocol_version = 1
       AND ROW(NEW.settlement_protocol_version, NEW.settlement_context, NEW.settlement_digest,
               NEW.uuid, NEW.sell_order_id, NEW.buy_order_id, NEW.seller_wallet_id, NEW.buyer_wallet_id,
               NEW.share_token_id, NEW.payment_asset_id, NEW.seller_address, NEW.buyer_address,
               NEW.share_amount, NEW.payment_amount, NEW.nonce, NEW.order_hash, NEW.expires_at, NEW.created_at)
           IS NOT DISTINCT FROM
           ROW(OLD.settlement_protocol_version, OLD.settlement_context, OLD.settlement_digest,
               OLD.uuid, OLD.sell_order_id, OLD.buy_order_id, OLD.seller_wallet_id, OLD.buyer_wallet_id,
               OLD.share_token_id, OLD.payment_asset_id, OLD.seller_address, OLD.buyer_address,
               OLD.share_amount, OLD.payment_amount, OLD.nonce, OLD.order_hash, OLD.expires_at, OLD.created_at)
       AND tokens_swap_has_current_party(NEW) THEN
        RETURN NEW;
    END IF;
"""


def refuse_parent_drift(apps, schema_editor):
    swaps = apps.get_model("tokens", "SwapOrder")._base_manager.using(schema_editor.connection.alias)
    failures = []
    total = 0
    for swap in swaps.select_related("sell_order", "buy_order").iterator():
        reasons = []
        for role, parent, wallet_id, address in (
            ("seller", swap.sell_order, swap.seller_wallet_id, swap.seller_address),
            ("buyer", swap.buy_order, swap.buyer_wallet_id, swap.buyer_address),
        ):
            if wallet_id != parent.wallet_id:
                reasons.append(f"{role} wallet differs from its order")
            if swap.settlement_protocol_version == 1:
                context = swap.settlement_context
                party = context.get(role) if isinstance(context, dict) else None
                if not isinstance(party, dict) or (
                    party.get("order_uuid") != str(parent.pk)
                    or party.get("owner_account_uuid") != str(parent.owner_account_id)
                    or party.get("wallet_uuid") != str(parent.wallet_id)
                    or str(party.get("address", "")).casefold() != parent.wallet_address.casefold()
                    or address.casefold() != parent.wallet_address.casefold()
                ):
                    reasons.append(f"{role} captured owner differs from its order")
        if reasons:
            total += 1
            if len(failures) < 20:
                failures.append(f"{swap.pk}: {', '.join(reasons)}")
    if total:
        raise RuntimeError(
            f"{total} swap(s) have inconsistent parent identity. Preserve their records and resolve the drift "
            "before retrying tokens.0040; no row has been rewritten. " + "; ".join(failures)
        )


def replace_parent_foreign_keys(schema_editor, restrict):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.conname, a.attname, parent.attname, c.confupdtype, c.confdeltype, "
            "c.condeferrable, c.condeferred, c.convalidated "
            "FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
            "JOIN pg_attribute parent ON parent.attrelid = c.confrelid AND parent.attnum = c.confkey[1] "
            "WHERE c.contype = 'f' AND c.conrelid = 'tokens_swaporder'::regclass "
            "AND c.confrelid = 'tokens_transferorder'::regclass "
            "AND cardinality(c.conkey) = 1 AND cardinality(c.confkey) = 1"
        )
        constraints = cursor.fetchall()
    expected = ("uuid", "a", "a", True, True, True) if restrict else ("uuid", "a", "r", False, False, True)
    if (
        len(constraints) != 2
        or {row[1] for row in constraints} != {"sell_order_id", "buy_order_id"}
        or any(tuple(row[2:]) != expected for row in constraints)
    ):
        raise RuntimeError("Unexpected swap-to-order foreign keys; no parent constraint has been replaced")
    behavior = "ON DELETE RESTRICT NOT DEFERRABLE" if restrict else "DEFERRABLE INITIALLY DEFERRED"
    for name, column, *_ in constraints:
        schema_editor.execute(f"ALTER TABLE tokens_swaporder DROP CONSTRAINT {schema_editor.quote_name(name)}")
        schema_editor.execute(
            f"ALTER TABLE tokens_swaporder ADD CONSTRAINT {schema_editor.quote_name(name)} "
            f"FOREIGN KEY ({schema_editor.quote_name(column)}) REFERENCES tokens_transferorder (uuid) {behavior}"
        )


def install_derivation(apps, schema_editor, participant_updates):
    original = import_module("tokens.migrations.0023_r0_owner_columns")
    body = original.DERIVE_FUNCTION
    if participant_updates:
        body = body.replace("BEGIN\n", "BEGIN\n" + PARTICIPANT_UPDATE, 1)
    for owner, parent in (("seller_wallet", "sell_order"), ("buyer_wallet", "buy_order")):
        names = original._derived_names(apps, "SwapOrder", owner, parent, "tokens", "TransferOrder", "wallet")
        schema_editor.execute(body.format(**names), params=None)


def protect_parent_identity(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    replace_parent_foreign_keys(schema_editor, True)
    schema_editor.execute(PARENT_GUARD, params=None)
    schema_editor.execute(CURRENT_PARTY, params=None)
    install_derivation(apps, schema_editor, True)


def unprotect_parent_identity(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    install_derivation(apps, schema_editor, False)
    schema_editor.execute(
        "DROP FUNCTION tokens_swap_has_current_party(tokens_swaporder);"
        "DROP TRIGGER tokens_order_owner_identity_guard ON tokens_transferorder;"
        "DROP FUNCTION tokens_order_owner_identity_guard();"
    )
    replace_parent_foreign_keys(schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [("tokens", "0039_swap_settlement_context")]
    operations = [
        migrations.RunPython(refuse_parent_drift, migrations.RunPython.noop),
        migrations.RunPython(protect_parent_identity, unprotect_parent_identity),
    ]
