from django.db import migrations

from shared.db.policy_sql import install, remove


def _install(apps, schema_editor):
    install(schema_editor)


def _remove(apps, schema_editor):
    remove(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0003_rls_roles_and_grants"),
        ("companies", "0001_initial"),
        ("documents", "0001_initial"),
        ("offerings", "0005_r0_owner_columns"),
        ("portfolios", "0001_initial"),
        ("tokens", "0024_r0_sharetoken_owner"),
        ("users", "0020_r0_owner_columns"),
        ("wallets", "0008_r0_owner_column"),
        ("whitelist", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_install, _remove),
    ]
