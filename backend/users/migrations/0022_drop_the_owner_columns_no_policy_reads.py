from django.db import migrations

DERIVED = (
    ("users_financialprofile", "financialprofile"),
    ("users_userpreferences", "userpreferences"),
    ("users_notification_preferences", "notificationpreferences"),
)


def drop_the_derivation(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, _model in DERIVED:
            name = f"{table}_user_is_derived"
            cursor.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
            cursor.execute(f"DROP FUNCTION IF EXISTS {name}()")


def _column(table, model):
    return migrations.SeparateDatabaseAndState(
        database_operations=[
            migrations.RunSQL(
                f"ALTER TABLE {table} DROP COLUMN IF EXISTS user_id",
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id bigint NULL",
            )
        ],
        state_operations=[migrations.RemoveField(model_name=model, name="user")],
    )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0021_trigger_types_from_the_column"),
        ("shared", "0010_policies_for_the_tables_that_had_none"),
    ]

    operations = [migrations.RunPython(drop_the_derivation, migrations.RunPython.noop)] + [
        _column(table, model) for table, model in DERIVED
    ]
