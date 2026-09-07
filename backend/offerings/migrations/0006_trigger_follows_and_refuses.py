from django.db import migrations

DERIVATIONS = (
    ("Offering", "token", ("tokens", "ShareToken")),
    ("Subscription", "offering", ("offerings", "Offering")),
)

AMENDED = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_company_id {parent_table}.{parent_owner}%TYPE;
BEGIN
    SELECT parent.{parent_owner} INTO parent_company_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_company_id IS NULL THEN
        RAISE EXCEPTION '{table}.company_id cannot be derived: {parent_fk} % has no company', NEW.{parent_fk};
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.{parent_fk} IS DISTINCT FROM OLD.{parent_fk}
           AND parent_company_id IS DISTINCT FROM OLD.{column} THEN
            RAISE EXCEPTION '{table}.{parent_fk} cannot move this row to another company, from % to %',
                OLD.{column}, parent_company_id;
        END IF;

        IF NEW.{column} IS NULL OR NEW.{column} IS NOT DISTINCT FROM OLD.{column} THEN
            NEW.{column} := parent_company_id;
        ELSIF NEW.{column} <> parent_company_id THEN
            RAISE EXCEPTION '{table}.company_id cannot be moved to %: {parent_fk} % names %',
                NEW.{column}, NEW.{parent_fk}, parent_company_id;
        END IF;
    ELSE
        IF NEW.{column} IS NULL THEN
            NEW.{column} := parent_company_id;
        ELSIF NEW.{column} <> parent_company_id THEN
            RAISE EXCEPTION '{table}.company_id % does not match its parent %', NEW.{column}, parent_company_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""

AS_0005_INSTALLED_IT = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger AS $derive$
DECLARE
    parent_company_id uuid;
BEGIN
    SELECT parent.{parent_owner} INTO parent_company_id
    FROM {parent_table} AS parent
    WHERE parent.{parent_pk} = NEW.{parent_fk};

    IF parent_company_id IS NULL THEN
        RAISE EXCEPTION '{table}.company_id cannot be derived: {parent_fk} % has no company', NEW.{parent_fk};
    END IF;

    IF NEW.{column} IS NULL THEN
        NEW.{column} := parent_company_id;
    ELSIF NEW.{column} <> parent_company_id THEN
        RAISE EXCEPTION '{table}.company_id % does not match its parent %', NEW.{column}, parent_company_id;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.{column} IS NOT NULL AND OLD.{column} <> NEW.{column} THEN
        RAISE EXCEPTION '{table}.company_id cannot change, from % to %', OLD.{column}, NEW.{column};
    END IF;

    RETURN NEW;
END;
$derive$ LANGUAGE plpgsql;
"""


def _names(apps, name, parent_field, parent_label):
    model = apps.get_model("offerings", name)
    parent = apps.get_model(*parent_label)
    table = model._meta.db_table
    return {
        "table": table,
        "column": model._meta.get_field("company").column,
        "parent_table": parent._meta.db_table,
        "parent_pk": parent._meta.pk.column,
        "parent_fk": model._meta.get_field(parent_field).column,
        "parent_owner": parent._meta.get_field("company").column,
        "function": f"{table}_company_is_derived",
    }


def _replace(apps, schema_editor, body):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for derivation in DERIVATIONS:
            cursor.execute(body.format(**_names(apps, *derivation)))


def follow_the_parent(apps, schema_editor):
    _replace(apps, schema_editor, AMENDED)


def refuse_any_change(apps, schema_editor):
    _replace(apps, schema_editor, AS_0005_INSTALLED_IT)


class Migration(migrations.Migration):

    dependencies = [("offerings", "0005_r0_owner_columns")]

    operations = [
        migrations.RunPython(follow_the_parent, refuse_any_change),
    ]
