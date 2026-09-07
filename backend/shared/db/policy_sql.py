from shared.db.policies import HELPERS, POLICIES

SUFFIXES = ("read", "insert", "update", "delete")


def install(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for name, body in HELPERS.items():
            cursor.execute(f"CREATE OR REPLACE FUNCTION {name}() RETURNS SETOF uuid LANGUAGE sql STABLE AS $${body}$$")

        for table, (readable, writable) in POLICIES.items():
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
            if not cursor.fetchone()[0]:
                continue
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            for suffix in SUFFIXES:
                cursor.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
            cursor.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({readable})")
            cursor.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({writable})")
            cursor.execute(
                f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({readable}) WITH CHECK ({writable})"
            )
            cursor.execute(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({writable})")


def remove(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for table in POLICIES:
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
            if not cursor.fetchone()[0]:
                continue
            for suffix in SUFFIXES:
                cursor.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
            cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

        for name in HELPERS:
            cursor.execute(f"DROP FUNCTION IF EXISTS {name}()")
