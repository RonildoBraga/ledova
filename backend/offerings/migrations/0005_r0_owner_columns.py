from django.db import migrations, models
from django.db.models import OuterRef, Subquery

ORDER_IS_LOAD_BEARING = (
    "Subscription derives its company from Offering.company_id, which this same pass fills, so DERIVATIONS "
    "must list a parent before its child. Unlike the users and wallets lanes this guard is reachable: "
    "reversing the two entries leaves every subscription without a company and raises here."
)

FUNCTION = """
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

TRIGGER = """
CREATE TRIGGER {trigger}
BEFORE INSERT OR UPDATE ON {table}
FOR EACH ROW EXECUTE FUNCTION {function}();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS {trigger} ON {table};"

DROP_FUNCTION = "DROP FUNCTION IF EXISTS {function}();"

DERIVATIONS = (
    ("Offering", "token", ("tokens", "ShareToken")),
    ("Subscription", "offering", ("offerings", "Offering")),
)


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
        "trigger": f"{table}_company_is_derived",
    }


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias

    for name, parent_field, parent_label in DERIVATIONS:
        model = apps.get_model("offerings", name)
        parent = apps.get_model(*parent_label)
        owner = Subquery(parent.objects.filter(pk=OuterRef(f"{parent_field}_id")).values("company_id")[:1])
        rows = model._base_manager.using(alias)
        filled = rows.filter(company_id__isnull=True).update(company_id=owner)
        remaining = rows.filter(company_id__isnull=True).count()
        print(f"  {model._meta.db_table}: {filled} row(s) backfilled, {remaining} without a company")
        if remaining:
            raise RuntimeError(
                f"{model._meta.db_table} has {remaining} row(s) whose parent has no company. {ORDER_IS_LOAD_BEARING}"
            )


def unfill(apps, schema_editor):
    for name, _, _ in DERIVATIONS:
        model = apps.get_model("offerings", name)
        model._base_manager.using(schema_editor.connection.alias).update(company_id=None)


def install_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for derivation in DERIVATIONS:
            names = _names(apps, *derivation)
            cursor.execute(FUNCTION.format(**names))
            cursor.execute(DROP_TRIGGER.format(**names))
            cursor.execute(TRIGGER.format(**names))


def drop_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for derivation in DERIVATIONS:
            names = _names(apps, *derivation)
            cursor.execute(DROP_TRIGGER.format(**names))
            cursor.execute(DROP_FUNCTION.format(**names))


HELP = "Owner, derived from {source} and held directly so a row-level security policy can read it"


def _field(source, null):
    return models.ForeignKey(
        null=null,
        on_delete=models.PROTECT,
        related_name="+",
        to="companies.company",
        help_text=HELP.format(source=source),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("offerings", "0004_protect_the_offering_token"),
        ("companies", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="offering", name="company", field=_field("token.company", True)),
        migrations.AddField(model_name="subscription", name="company", field=_field("offering.company", True)),
        migrations.RunPython(backfill, unfill),
        migrations.AlterField(model_name="offering", name="company", field=_field("token.company", False)),
        migrations.AlterField(model_name="subscription", name="company", field=_field("offering.company", False)),
        migrations.RunPython(install_triggers, drop_triggers),
    ]
