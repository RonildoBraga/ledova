from django.db import migrations

TABLES = ("NotificationPreferences", "UserPreferences", "FinancialProfile")

AMENDED = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_user_id {parent_table}.user_id%TYPE;
BEGIN
    SELECT profile.user_id INTO parent_user_id
    FROM {parent_table} AS profile
    WHERE profile.{parent_pk} = NEW.{parent_fk};

    IF parent_user_id IS NULL THEN
        RAISE EXCEPTION '{table}.user_id cannot be derived: user_profile % has no user', NEW.{parent_fk};
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk} THEN
            RAISE EXCEPTION '{table}.{parent_fk} cannot change, from % to %', OLD.{parent_fk}, NEW.{parent_fk};
        END IF;

        IF NEW.{column} IS NULL OR NEW.{column} IS NOT DISTINCT FROM OLD.{column} THEN
            NEW.{column} := parent_user_id;
        ELSIF NEW.{column} <> parent_user_id THEN
            RAISE EXCEPTION '{table}.user_id cannot be moved to %: user_profile % names %',
                NEW.{column}, NEW.{parent_fk}, parent_user_id;
        END IF;
    ELSE
        IF NEW.{column} IS NULL THEN
            NEW.{column} := parent_user_id;
        ELSIF NEW.{column} <> parent_user_id THEN
            RAISE EXCEPTION '{table}.user_id % does not match user_profile.user_id %', NEW.{column}, parent_user_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

AS_0020_INSTALLED_IT = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_user_id integer;
BEGIN
    SELECT profile.user_id INTO parent_user_id
    FROM {parent_table} AS profile
    WHERE profile.{parent_pk} = NEW.{parent_fk};

    IF parent_user_id IS NULL THEN
        RAISE EXCEPTION '{table}.user_id cannot be derived: user_profile % has no user', NEW.{parent_fk};
    END IF;

    IF NEW.{column} IS NULL THEN
        NEW.{column} := parent_user_id;
    ELSIF NEW.{column} <> parent_user_id THEN
        RAISE EXCEPTION '{table}.user_id % does not match user_profile.user_id %', NEW.{column}, parent_user_id;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.{column} IS NOT NULL AND OLD.{column} <> NEW.{column} THEN
        RAISE EXCEPTION '{table}.user_id cannot change, from % to %', OLD.{column}, NEW.{column};
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""


def _names(apps, name):
    model = apps.get_model("users", name)
    parent = apps.get_model("users", "UserProfile")
    table = model._meta.db_table
    return {
        "table": table,
        "column": model._meta.get_field("user").column,
        "parent_table": parent._meta.db_table,
        "parent_pk": parent._meta.pk.column,
        "parent_fk": model._meta.get_field("user_profile").column,
        "function": f"{table}_user_is_derived",
    }


def _replace(apps, schema_editor, body):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for name in TABLES:
            cursor.execute(body.format(**_names(apps, name)))


def follow_the_parent(apps, schema_editor):
    _replace(apps, schema_editor, AMENDED)


def refuse_any_change(apps, schema_editor):
    _replace(apps, schema_editor, AS_0020_INSTALLED_IT)


class Migration(migrations.Migration):

    dependencies = [("users", "0020_r0_owner_columns")]

    operations = [
        migrations.RunPython(follow_the_parent, refuse_any_change),
    ]
