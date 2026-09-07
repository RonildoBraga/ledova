from django.db import migrations

AMENDED = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_account_id {parent_table}.{parent_owner}%TYPE;
BEGIN
    SELECT parent.{parent_owner} INTO parent_account_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_account_id IS NULL THEN
        RAISE EXCEPTION '{table}.user_account_id cannot be derived: wallet % has no user_account', NEW.{parent_fk};
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk}
           AND parent_account_id IS DISTINCT FROM OLD.{column} THEN
            RAISE EXCEPTION '{table}.{parent_fk} cannot move this row to another user_account, from % to %',
                OLD.{column}, parent_account_id;
        END IF;

        IF NEW.{column} IS NULL OR NEW.{column} IS NOT DISTINCT FROM OLD.{column} THEN
            NEW.{column} := parent_account_id;
        ELSIF NEW.{column} <> parent_account_id THEN
            RAISE EXCEPTION '{table}.user_account_id cannot be moved to %: wallet % names %',
                NEW.{column}, NEW.{parent_fk}, parent_account_id;
        END IF;
    ELSE
        IF NEW.{column} IS NULL THEN
            NEW.{column} := parent_account_id;
        ELSIF NEW.{column} <> parent_account_id THEN
            RAISE EXCEPTION '{table}.user_account_id % does not match wallet.user_account_id %',
                NEW.{column}, parent_account_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

AS_0008_INSTALLED_IT = """
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

    IF TG_OP = 'UPDATE' AND OLD.{column} IS NOT NULL AND OLD.{column} <> NEW.{column} THEN
        RAISE EXCEPTION '{table}.user_account_id cannot change, from % to %', OLD.{column}, NEW.{column};
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""


def _names(apps):
    model = apps.get_model("wallets", "Transaction")
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
    }


def _replace(apps, schema_editor, body):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(body.format(**_names(apps)))


def follow_the_parent(apps, schema_editor):
    _replace(apps, schema_editor, AMENDED)


def refuse_any_change(apps, schema_editor):
    _replace(apps, schema_editor, AS_0008_INSTALLED_IT)


class Migration(migrations.Migration):

    dependencies = [("wallets", "0008_r0_owner_column")]

    operations = [
        migrations.RunPython(follow_the_parent, refuse_any_change),
    ]
