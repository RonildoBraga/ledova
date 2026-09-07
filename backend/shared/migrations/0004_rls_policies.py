from django.db import migrations

from shared.db.policies import HELPERS, POLICIES


def _install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for name, body in HELPERS.items():
            cursor.execute(f"CREATE OR REPLACE FUNCTION {name}() RETURNS SETOF uuid LANGUAGE sql STABLE AS $${body}$$")

        for table, (readable, writable) in POLICIES.items():
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            cursor.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
            cursor.execute(
                f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({readable}) WITH CHECK ({writable})"
            )


def _remove(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for table in POLICIES:
            cursor.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

        for name in HELPERS:
            cursor.execute(f"DROP FUNCTION IF EXISTS {name}()")


class Migration(migrations.Migration):

    dependencies = [
        ("shared", "0003_rls_roles_and_grants"),
        ("companies", "0001_initial"),
        ("documents", "0001_initial"),
        ("offerings", "0005_r0_owner_columns"),
        ("portfolios", "0001_initial"),
        ("tokens", "0001_initial"),
        ("users", "0020_r0_owner_columns"),
        ("wallets", "0008_r0_owner_column"),
        ("whitelist", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_install, _remove),
    ]
