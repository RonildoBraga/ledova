from django.db import migrations

DERIVED = (
    ("users_financialprofile", "user_id"),
    ("users_userpreferences", "user_id"),
    ("users_notification_preferences", "user_id"),
)


def drop_the_derivation(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, column in DERIVED:
            name = f"{table}_user_is_derived"
            cursor.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
            cursor.execute(f"DROP FUNCTION IF EXISTS {name}()")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0021_trigger_types_from_the_column"),
        ("shared", "0010_policies_for_the_tables_that_had_none"),
    ]

    operations = [
        migrations.RunPython(drop_the_derivation, migrations.RunPython.noop),
        migrations.RemoveField(model_name="financialprofile", name="user"),
        migrations.RemoveField(model_name="userpreferences", name="user"),
        migrations.RemoveField(model_name="notificationpreferences", name="user"),
    ]
