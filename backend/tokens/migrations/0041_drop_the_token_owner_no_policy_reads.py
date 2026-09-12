from django.db import migrations

ADD_BACK_NULLABLE = "ALTER TABLE tokens_sharetoken ADD COLUMN IF NOT EXISTS owner_id bigint NULL"
DROP = "ALTER TABLE tokens_sharetoken DROP COLUMN IF EXISTS owner_id"


def drop_the_derivation(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    name = "tokens_sharetoken_owner_id_is_derived"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"DROP TRIGGER IF EXISTS {name} ON tokens_sharetoken")
        cursor.execute(f"DROP FUNCTION IF EXISTS {name}()")


class Migration(migrations.Migration):
    dependencies = [
        ("tokens", "0040_swap_parent_identity"),
        ("shared", "0010_policies_for_the_tables_that_had_none"),
    ]

    operations = [
        migrations.RunPython(drop_the_derivation, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(DROP, ADD_BACK_NULLABLE)],
            state_operations=[migrations.RemoveField(model_name="sharetoken", name="owner")],
        ),
    ]
