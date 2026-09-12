from django.db import migrations

from shared.db.policy_sql import install


def reinstall(apps, schema_editor):
    install(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0008_scoped_role_table_grants"),
    ]

    operations = [migrations.RunPython(reinstall, migrations.RunPython.noop)]
