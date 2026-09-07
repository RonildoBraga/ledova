from django.conf import settings
from django.db import migrations, models
from django.db.models import OuterRef, Subquery

DERIVE_FUNCTION = """
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

TRIGGER = """
CREATE TRIGGER {trigger}
BEFORE INSERT OR UPDATE ON {table}
FOR EACH ROW EXECUTE FUNCTION {function}();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS {trigger} ON {table};"

DROP_FUNCTION = "DROP FUNCTION IF EXISTS {function}();"

HELP = (
    "Owner, derived from company.owner and held directly so a row-level "
    "security policy can read it without joining companies"
)


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
        "trigger": f"{table}_{column}_is_derived",
    }


def _settle_deferred_constraints(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE;")


def backfill(apps, schema_editor):
    _settle_deferred_constraints(schema_editor)
    alias = schema_editor.connection.alias
    token = apps.get_model("tokens", "ShareToken")
    company = apps.get_model("companies", "Company")
    rows = token._base_manager.using(alias)

    owner = Subquery(company._base_manager.using(alias).filter(pk=OuterRef("company_id")).values("owner_id")[:1])
    filled = rows.filter(owner_id__isnull=True).update(owner_id=owner)
    remaining = rows.filter(owner_id__isnull=True).count()

    print(f"  {token._meta.db_table}.owner: {filled} filled, {remaining} left null")

    if remaining:
        raise RuntimeError(
            f"{token._meta.db_table}.owner has {remaining} row(s) whose company has no owner. "
            f"Both links are non-nullable, so this cannot happen under the current schema."
        )


def unfill(apps, schema_editor):
    _settle_deferred_constraints(schema_editor)
    alias = schema_editor.connection.alias
    apps.get_model("tokens", "ShareToken")._base_manager.using(alias).update(owner_id=None)


def install_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    names = _names(apps)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DERIVE_FUNCTION.format(**names))
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(TRIGGER.format(**names))


def drop_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    names = _names(apps)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DROP_TRIGGER.format(**names))
        cursor.execute(DROP_FUNCTION.format(**names))


def _owner(null):
    return models.ForeignKey(
        null=null, on_delete=models.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL, help_text=HELP
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tokens", "0023_r0_owner_columns"),
        ("companies", "0006_company_document_private_storage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="sharetoken", name="owner", field=_owner(True)),
        migrations.RunPython(backfill, unfill),
        migrations.AlterField(model_name="sharetoken", name="owner", field=_owner(False)),
        migrations.RunPython(install_trigger, drop_trigger),
    ]
