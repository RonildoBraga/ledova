from django.db import migrations, models
from django.db.models import OuterRef, Subquery

DERIVE_FUNCTION = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_owner_id uuid;
BEGIN
    SELECT parent.{parent_owner} INTO parent_owner_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_owner_id IS NULL THEN
        RAISE EXCEPTION '{table}.{column} cannot be derived: {parent_table} % has no {parent_owner}', NEW.{parent_fk};
    END IF;

    IF NEW.{column} IS NULL THEN
        NEW.{column} := parent_owner_id;
    ELSIF NEW.{column} <> parent_owner_id THEN
        RAISE EXCEPTION '{table}.{column} % does not match {parent_table}.{parent_owner} %',
            NEW.{column}, parent_owner_id;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.{column} IS NOT NULL AND OLD.{column} <> NEW.{column} THEN
        RAISE EXCEPTION '{table}.{column} cannot change, from % to %', OLD.{column}, NEW.{column};
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $check$
DECLARE
    wallet_address_of_record text;
    order_wallet_id uuid;
BEGIN
    IF NEW.{column} IS NULL THEN
        RAISE EXCEPTION '{table}.{column} is required: the service holds the caller''s wallet and must supply it';
    END IF;

    SELECT parent.{parent_address} INTO wallet_address_of_record
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{column};

    IF wallet_address_of_record IS NULL THEN
        RAISE EXCEPTION '{table}.{column} % names no wallet', NEW.{column};
    END IF;

    IF lower(wallet_address_of_record) <> lower(NEW.{address_column}) THEN
        RAISE EXCEPTION '{table}.{column} % holds address % but the challenge names %',
            NEW.{column}, wallet_address_of_record, NEW.{address_column};
    END IF;

    IF NEW.{order_fk} IS NOT NULL THEN
        SELECT o.{order_wallet} INTO order_wallet_id
        FROM {order_table} AS o
        WHERE o.{order_pk} = NEW.{order_fk};

        IF order_wallet_id IS NOT NULL AND order_wallet_id <> NEW.{column} THEN
            RAISE EXCEPTION '{table}.{column} % is not the wallet that owns order %', NEW.{column}, NEW.{order_fk};
        END IF;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.{column} IS NOT NULL AND OLD.{column} <> NEW.{column} THEN
        RAISE EXCEPTION '{table}.{column} cannot change, from % to %', OLD.{column}, NEW.{column};
    END IF;

    RETURN NEW;
END;
$check$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER {trigger}
BEFORE INSERT OR UPDATE ON {table}
FOR EACH ROW EXECUTE FUNCTION {function}();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS {trigger} ON {table};"

DROP_FUNCTION = "DROP FUNCTION IF EXISTS {function}();"

DERIVED = (
    ("CapitalIncreaseRequest", "company", "token", "tokens", "ShareToken", "company"),
    ("ShareIssuanceRequest", "company", "token", "tokens", "ShareToken", "company"),
    ("SwapOrder", "seller_wallet", "sell_order", "tokens", "TransferOrder", "wallet"),
    ("SwapOrder", "buyer_wallet", "buy_order", "tokens", "TransferOrder", "wallet"),
)


def _derived_names(apps, model_name, column, parent_fk, parent_app, parent_model, parent_owner):
    model = apps.get_model("tokens", model_name)
    parent = apps.get_model(parent_app, parent_model)
    table = model._meta.db_table
    column_name = model._meta.get_field(column).column
    return {
        "table": table,
        "column": column_name,
        "parent_table": parent._meta.db_table,
        "parent_pk": parent._meta.pk.column,
        "parent_fk": model._meta.get_field(parent_fk).column,
        "parent_owner": parent._meta.get_field(parent_owner).column,
        "function": f"{table}_{column_name}_is_derived",
        "trigger": f"{table}_{column_name}_is_derived",
    }


def _challenge_names(apps):
    model = apps.get_model("tokens", "SigningChallenge")
    wallet = apps.get_model("wallets", "Wallet")
    order = apps.get_model("tokens", "TransferOrder")
    table = model._meta.db_table
    return {
        "table": table,
        "column": model._meta.get_field("wallet").column,
        "address_column": model._meta.get_field("wallet_address").column,
        "parent_table": wallet._meta.db_table,
        "parent_pk": wallet._meta.pk.column,
        "parent_address": wallet._meta.get_field("address").column,
        "order_fk": model._meta.get_field("order").column,
        "order_table": order._meta.db_table,
        "order_pk": order._meta.pk.column,
        "order_wallet": order._meta.get_field("wallet").column,
        "function": f"{table}_wallet_is_checked",
        "trigger": f"{table}_wallet_is_checked",
    }


def _fill(rows, column, owner):
    return rows.filter(**{f"{column}__isnull": True}).update(**{column: owner})


def backfill(apps, schema_editor):
    _settle_deferred_constraints(schema_editor)
    alias = schema_editor.connection.alias
    counts = {}

    for model_name, column, parent_fk, parent_app, parent_model, parent_owner in DERIVED:
        model = apps.get_model("tokens", model_name)
        parent = apps.get_model(parent_app, parent_model)
        rows = model._base_manager.using(alias)
        owner = Subquery(
            parent._base_manager.using(alias).filter(pk=OuterRef(f"{parent_fk}_id")).values(f"{parent_owner}_id")[:1]
        )
        filled = _fill(rows, f"{column}_id", owner)
        remaining = rows.filter(**{f"{column}_id__isnull": True}).count()
        counts[f"{model._meta.db_table}.{column}"] = (filled, remaining)
        if remaining:
            raise RuntimeError(
                f"{model._meta.db_table}.{column} has {remaining} row(s) whose {parent_fk} has no {parent_owner}. "
                f"Both links are non-nullable, so this cannot happen under the current schema."
            )

    counts.update(_backfill_challenges(apps, alias))

    for name, (filled, remaining) in counts.items():
        print(f"  {name}: {filled} filled, {remaining} left null")


def _settle_deferred_constraints(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE;")


def _backfill_challenges(apps, alias):
    challenge = apps.get_model("tokens", "SigningChallenge")
    order = apps.get_model("tokens", "TransferOrder")
    wallet = apps.get_model("wallets", "Wallet")
    rows = challenge._base_manager.using(alias)

    through_order = Subquery(order._base_manager.using(alias).filter(pk=OuterRef("order_id")).values("wallet_id")[:1])
    by_order = rows.filter(wallet_id__isnull=True, order_id__isnull=False).update(wallet_id=through_order)

    by_address = 0
    ambiguous = 0
    orphan = 0
    for row in rows.filter(wallet_id__isnull=True).iterator():
        candidates = list(
            wallet._base_manager.using(alias)
            .filter(address__iexact=row.wallet_address)
            .values_list("pk", flat=True)[:2]
        )
        if len(candidates) == 1:
            rows.filter(pk=row.pk).update(wallet_id=candidates[0])
            by_address += 1
        elif len(candidates) > 1:
            ambiguous += 1
        else:
            orphan += 1

    print(f"  signing_challenges: {by_order} by order, {by_address} by address, {ambiguous} ambiguous, {orphan} orphan")
    return {"signing_challenges.wallet": (by_order + by_address, ambiguous + orphan)}


def unfill(apps, schema_editor):
    _settle_deferred_constraints(schema_editor)
    alias = schema_editor.connection.alias
    for model_name, column, _fk, _app, _model, _owner in DERIVED:
        apps.get_model("tokens", model_name)._base_manager.using(alias).update(**{f"{column}_id": None})
    apps.get_model("tokens", "SigningChallenge")._base_manager.using(alias).update(wallet_id=None)


def install_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for spec in DERIVED:
            names = _derived_names(apps, *spec)
            cursor.execute(DERIVE_FUNCTION.format(**names))
            cursor.execute(DROP_TRIGGER.format(**names))
            cursor.execute(TRIGGER.format(**names))
        names = _challenge_names(apps)
        cursor.execute(CHECK_FUNCTION.format(**names))
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(TRIGGER.format(**names))


def drop_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    _settle_deferred_constraints(schema_editor)
    with schema_editor.connection.cursor() as cursor:
        for spec in DERIVED:
            names = _derived_names(apps, *spec)
            cursor.execute(DROP_TRIGGER.format(**names))
            cursor.execute(DROP_FUNCTION.format(**names))
        names = _challenge_names(apps)
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(DROP_FUNCTION.format(**names))


COMPANY_HELP = "Owner, derived from token.company and held directly so a row-level security policy can read it"
SELLER_HELP = "Seller, derived from sell_order.wallet and held directly so a row-level security policy can read it"
BUYER_HELP = "Buyer, derived from buy_order.wallet and held directly so a row-level security policy can read it"
CHALLENGE_HELP = (
    "Owner. Supplied by the service, which holds the authenticated caller's wallet; null only for rows "
    "written before this column, whose address named no wallet or more than one"
)


def _company(null):
    return models.ForeignKey(
        null=null, on_delete=models.PROTECT, related_name="+", to="companies.company", help_text=COMPANY_HELP
    )


def _wallet(null, help_text, blank=False):
    return models.ForeignKey(
        null=null,
        blank=blank,
        on_delete=models.PROTECT,
        related_name="+",
        to="wallets.wallet",
        help_text=help_text,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0022_swap_nonce_is_unique"),
        ("companies", "0006_company_document_private_storage"),
        ("wallets", "0006_delete_fiattransaction_drop_unread_columns"),
    ]

    operations = [
        migrations.AddField(model_name="capitalincreaserequest", name="company", field=_company(True)),
        migrations.AddField(model_name="shareissuancerequest", name="company", field=_company(True)),
        migrations.AddField(model_name="swaporder", name="seller_wallet", field=_wallet(True, SELLER_HELP)),
        migrations.AddField(model_name="swaporder", name="buyer_wallet", field=_wallet(True, BUYER_HELP)),
        migrations.AddField(
            model_name="signingchallenge", name="wallet", field=_wallet(True, CHALLENGE_HELP, blank=True)
        ),
        migrations.RunPython(backfill, unfill),
        migrations.AlterField(model_name="capitalincreaserequest", name="company", field=_company(False)),
        migrations.AlterField(model_name="shareissuancerequest", name="company", field=_company(False)),
        migrations.AlterField(model_name="swaporder", name="seller_wallet", field=_wallet(False, SELLER_HELP)),
        migrations.AlterField(model_name="swaporder", name="buyer_wallet", field=_wallet(False, BUYER_HELP)),
        migrations.RunPython(install_triggers, drop_triggers),
    ]
