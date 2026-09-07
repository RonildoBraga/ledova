from django.conf import settings
from django.db import migrations, models
from django.db.models import OuterRef, Subquery

TABLES = ("NotificationPreferences", "UserPreferences", "FinancialProfile")

SKIPPED_ON_SQLITE = (
    "The derive-and-refuse trigger is PostgreSQL only. SQLite has no plpgsql, "
    "and the column exists for a PostgreSQL row-level security policy, so a "
    "SQLite deployment has nothing for the trigger to protect."
)

FUNCTION = """
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

    IF TG_OP = 'UPDATE' AND OLD.{column} IS DISTINCT FROM NEW.{column} THEN
        RAISE EXCEPTION '{table}.user_id cannot change, from % to %', OLD.{column}, NEW.{column};
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

DROP = """
DROP TRIGGER IF EXISTS {trigger} ON {table};
DROP FUNCTION IF EXISTS {function}();
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
        "trigger": f"{table}_user_is_derived",
    }


def backfill(apps, schema_editor):
    profile = apps.get_model("users", "UserProfile")
    alias = schema_editor.connection.alias
    owner = Subquery(profile.objects.filter(pk=OuterRef("user_profile_id")).values("user_id")[:1])

    for name in TABLES:
        model = apps.get_model("users", name)
        rows = model._base_manager.using(alias)
        filled = rows.filter(user_id__isnull=True).update(user_id=owner)
        remaining = rows.filter(user_id__isnull=True).count()
        print(f"  {model._meta.db_table}: {filled} row(s) backfilled, {remaining} without an owner")
        if remaining:
            raise RuntimeError(f"{model._meta.db_table} has {remaining} row(s) whose user_profile has no user")


def unfill(apps, schema_editor):
    for name in TABLES:
        model = apps.get_model("users", name)
        model._base_manager.using(schema_editor.connection.alias).update(user_id=None)


def install_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for name in TABLES:
            names = _names(apps, name)
            cursor.execute(FUNCTION.format(**names))
            cursor.execute(DROP.format(**names).split(";")[0] + ";")
            cursor.execute(TRIGGER.format(**names))


def drop_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for name in TABLES:
            cursor.execute(DROP.format(**_names(apps, name)))


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0019_alter_investorclassification_status_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationpreferences",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=models.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text=(
                    "Owner, derived from user_profile.user and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.AddField(
            model_name="userpreferences",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=models.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text=(
                    "Owner, derived from user_profile.user and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.AddField(
            model_name="financialprofile",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=models.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text=(
                    "Owner, derived from user_profile.user and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.RunPython(backfill, unfill),
        migrations.AlterField(
            model_name="notificationpreferences",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text=(
                    "Owner, derived from user_profile.user and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.AlterField(
            model_name="userpreferences",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text=(
                    "Owner, derived from user_profile.user and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.AlterField(
            model_name="financialprofile",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text=(
                    "Owner, derived from user_profile.user and held directly so a "
                    "row-level security policy can read it"
                ),
            ),
        ),
        migrations.RunPython(install_triggers, drop_triggers),
    ]
