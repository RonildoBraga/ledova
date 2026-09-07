from django.db import migrations, models
from django.db.models import OuterRef, Subquery

TABLE = "Transaction"

REVERSE_ORDER = (
    "Operations reverse back to front, so drop_trigger runs before unfill sets every user_account_id to "
    "NULL. An operation appended after install_trigger would move that boundary, and unfill would then hit "
    "the trigger's own cannot-change guard and the reverse would be impossible."
)

UNREACHABLE_TODAY = (
    "Wallet.user_account and Transaction.wallet are both non-nullable, so neither this guard nor the "
    "trigger's matching RAISE can fire under the current schema. Both are here for the R0 lanes whose "
    "parent link is nullable, where the same shape does fire."
)

SKIPPED_ON_SQLITE = (
    "The derive-and-refuse trigger is PostgreSQL only. SQLite has no plpgsql, and the column exists "
    "for a PostgreSQL row-level security policy, so a SQLite deployment has nothing for it to protect."
)

FUNCTION = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_account_id uuid;
BEGIN
    SELECT parent.{parent_owner} INTO parent_account_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_account_id IS NULL THEN
        RAISE EXCEPTION '{table}.user_account_id cannot be derived: wallet % has no user_account', NEW.{parent_fk};
    END IF;

    IF NEW.{column} IS NULL THEN
        NEW.{column} := parent_account_id;
    ELSIF NEW.{column} <> parent_account_id THEN
        RAISE EXCEPTION '{table}.user_account_id % does not match wallet.user_account_id %',
            NEW.{column}, parent_account_id;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.{column} IS DISTINCT FROM NEW.{column} THEN
        RAISE EXCEPTION '{table}.user_account_id cannot change, from % to %', OLD.{column}, NEW.{column};
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER {trigger}
BEFORE INSERT OR UPDATE ON {table}
FOR EACH ROW EXECUTE FUNCTION {function}();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS {trigger} ON {table};"

DROP_FUNCTION = "DROP FUNCTION IF EXISTS {function}();"


def _names(apps):
    model = apps.get_model("wallets", TABLE)
    parent = apps.get_model("wallets", "Wallet")
    table = model._meta.db_table
    return {
        "table": table,
        "column": model._meta.get_field("user_account").column,
        "parent_table": parent._meta.db_table,
        "parent_pk": parent._meta.pk.column,
        "parent_fk": model._meta.get_field("wallet").column,
        "parent_owner": parent._meta.get_field("user_account").column,
        "function": f"{table}_user_account_is_derived",
        "trigger": f"{table}_user_account_is_derived",
    }


def backfill(apps, schema_editor):
    model = apps.get_model("wallets", TABLE)
    wallet = apps.get_model("wallets", "Wallet")
    rows = model._base_manager.using(schema_editor.connection.alias)
    owner = Subquery(wallet.objects.filter(pk=OuterRef("wallet_id")).values("user_account_id")[:1])

    filled = rows.filter(user_account_id__isnull=True).update(user_account_id=owner)
    remaining = rows.filter(user_account_id__isnull=True).count()
    print(f"  {model._meta.db_table}: {filled} row(s) backfilled, {remaining} without an owner")
    if remaining:
        raise RuntimeError(
            f"{model._meta.db_table} has {remaining} row(s) whose wallet has no user_account. {UNREACHABLE_TODAY}"
        )


def unfill(apps, schema_editor):
    connection = schema_editor.connection
    model = apps.get_model("wallets", TABLE)
    if connection.vendor == "postgresql":
        names = _names(apps)
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [names["trigger"]])
            if cursor.fetchone()[0]:
                raise RuntimeError(f"{names['trigger']} is still installed. {REVERSE_ORDER}")
    model._base_manager.using(connection.alias).update(user_account_id=None)


def install_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    names = _names(apps)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FUNCTION.format(**names))
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(TRIGGER.format(**names))


def drop_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        names = _names(apps)
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(DROP_FUNCTION.format(**names))


class Migration(migrations.Migration):

    dependencies = [
        ("wallets", "0007_transaction_deducted_amount_transaction_deducted_fee"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="user_account",
            field=models.ForeignKey(
                null=True,
                on_delete=models.CASCADE,
                related_name="+",
                to="users.useraccount",
                help_text=(
                    "Owner, derived from wallet.user_account and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.RunPython(backfill, unfill),
        migrations.AlterField(
            model_name="transaction",
            name="user_account",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="+",
                to="users.useraccount",
                help_text=(
                    "Owner, derived from wallet.user_account and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.RunPython(install_trigger, drop_trigger),
    ]
