from django.db import migrations

from shared.db.policy_sql import install


def reinstall(apps, schema_editor):
    install(schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("shared", "0006_account_insert_by_director"),
        ("tokens", "0025_a_token_cannot_change_company"),
    ]

    operations = [migrations.RunPython(reinstall, migrations.RunPython.noop)]
