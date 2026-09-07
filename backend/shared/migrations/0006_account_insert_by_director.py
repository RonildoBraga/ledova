from django.db import migrations

from shared.db.policy_sql import install


def _reinstall(apps, schema_editor):
    install(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0005_rls_principal_missing_ok"),
    ]

    operations = [
        migrations.RunPython(_reinstall, migrations.RunPython.noop),
    ]
