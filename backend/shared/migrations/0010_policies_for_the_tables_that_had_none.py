from django.db import migrations

from shared.db.policy_sql import install


def reinstall(apps, schema_editor):
    install(schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("shared", "0009_policies_require_a_principal"),
        ("tokens", "0040_swap_parent_identity"),
        ("wallets", "0019_chain_observations"),
    ]

    operations = [migrations.RunPython(reinstall, migrations.RunPython.noop)]
