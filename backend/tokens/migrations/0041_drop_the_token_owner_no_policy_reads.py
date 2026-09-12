from django.db import migrations


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
        migrations.RemoveField(model_name="sharetoken", name="owner"),
    ]
