from django.db import migrations

WITHOUT_REPARENTING = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_owner_id {parent_table}.{parent_owner}%TYPE;
BEGIN
    SELECT parent.{parent_owner} INTO parent_owner_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_owner_id IS NULL THEN
        RAISE EXCEPTION '{table}.{column} cannot be derived: {parent_table} % has no {parent_owner}', NEW.{parent_fk};
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk} THEN
            RAISE EXCEPTION '{table}.{parent_fk} cannot change, from % to %', OLD.{parent_fk}, NEW.{parent_fk};
        END IF;

        IF NEW.{column} IS NULL OR NEW.{column} IS NOT DISTINCT FROM OLD.{column} THEN
            NEW.{column} := parent_owner_id;
        ELSIF NEW.{column} <> parent_owner_id THEN
            RAISE EXCEPTION '{table}.{column} cannot be moved to %: {parent_table} % names %',
                NEW.{column}, NEW.{parent_fk}, parent_owner_id;
        END IF;
    ELSE
        IF NEW.{column} IS NULL THEN
            NEW.{column} := parent_owner_id;
        ELSIF NEW.{column} <> parent_owner_id THEN
            RAISE EXCEPTION '{table}.{column} % does not match {parent_table}.{parent_owner} %',
                NEW.{column}, parent_owner_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

WITH_REPARENTING = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_owner_id {parent_table}.{parent_owner}%TYPE;
BEGIN
    SELECT parent.{parent_owner} INTO parent_owner_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_owner_id IS NULL THEN
        RAISE EXCEPTION '{table}.{column} cannot be derived: {parent_table} % has no {parent_owner}', NEW.{parent_fk};
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.{column} IS NULL OR NEW.{column} IS NOT DISTINCT FROM OLD.{column} THEN
            NEW.{column} := parent_owner_id;
        ELSIF NEW.{column} <> parent_owner_id THEN
            RAISE EXCEPTION '{table}.{column} cannot be moved to %: {parent_table} % names %',
                NEW.{column}, NEW.{parent_fk}, parent_owner_id;
        END IF;
    ELSE
        IF NEW.{column} IS NULL THEN
            NEW.{column} := parent_owner_id;
        ELSIF NEW.{column} <> parent_owner_id THEN
            RAISE EXCEPTION '{table}.{column} % does not match {parent_table}.{parent_owner} %',
                NEW.{column}, parent_owner_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""


def _names(apps):
    model = apps.get_model("tokens", "ShareToken")
    parent = apps.get_model("companies", "Company")
    table = model._meta.db_table
    column = model._meta.get_field("owner").column
    return {
        "table": table,
        "column": column,
        "parent_table": parent._meta.db_table,
        "parent_pk": parent._meta.pk.column,
        "parent_fk": model._meta.get_field("company").column,
        "parent_owner": parent._meta.get_field("owner").column,
        "function": f"{table}_{column}_is_derived",
    }


def _replace(body):
    def run(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(body.format(**_names(apps)))

    return run


class Migration(migrations.Migration):

    dependencies = [("tokens", "0024_r0_sharetoken_owner")]

    operations = [migrations.RunPython(_replace(WITHOUT_REPARENTING), _replace(WITH_REPARENTING))]
