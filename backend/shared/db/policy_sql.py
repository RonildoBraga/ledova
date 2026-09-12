from django.conf import settings

from shared.db.policies import (
    ADMITTED,
    AWAITING_RLS,
    FRAMEWORK,
    HELPERS,
    INSERTABLE,
    NOT_TENANCY,
    POLICIES,
    REACHED_DESPITE_OPERATOR_ONLY,
)

SUFFIXES = ("read", "insert", "update", "delete")

NOT_YET_CREATED = (
    "The catalogue says the app role reaches {tables}, and the grant ran before they existed. "
    "Default privileges now deny them, so leaving this silent would take the role's access away "
    "rather than leave it unchanged. Add the migration that creates them to this migration's "
    "dependencies."
)


def install(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for name, body in HELPERS.items():
            cursor.execute(f"CREATE OR REPLACE FUNCTION {name}() RETURNS SETOF uuid LANGUAGE sql STABLE AS $${body}$$")

    install_tables(schema_editor, POLICIES)


def reachable_by_the_app_role() -> tuple[str, ...]:
    return (*POLICIES, *FRAMEWORK, *NOT_TENANCY, *AWAITING_RLS, *REACHED_DESPITE_OPERATOR_ONLY)


def grant_reachable_tables(schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    app_role = settings.RLS_ROLES["app"]
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT quote_ident(%s), quote_ident(current_user)", [app_role])
        quoted_app, quoted_owner = cursor.fetchone()
        cursor.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {quoted_app}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted_owner} IN SCHEMA public "
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {quoted_app}"
        )
        missing = []
        for table in reachable_by_the_app_role():
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
            if not cursor.fetchone()[0]:
                missing.append(table)
                continue
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {quoted_app}")
    if missing:
        raise RuntimeError(NOT_YET_CREATED.format(tables=", ".join(sorted(missing))))


def install_tables(schema_editor, tables):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        for table in tables:
            readable, writable = POLICIES[table]
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
            if not cursor.fetchone()[0]:
                continue
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            for suffix in SUFFIXES:
                cursor.execute(f"DROP POLICY IF EXISTS {table}_{suffix} ON {table}")
            cursor.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({ADMITTED} AND ({readable}))")
            insertable = INSERTABLE.get(table, writable)
            cursor.execute(
                f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({ADMITTED} AND ({insertable}))"
            )
            cursor.execute(
                f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({ADMITTED} AND ({readable})) "
                f"WITH CHECK ({ADMITTED} AND ({writable}))"
            )
            cursor.execute(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({ADMITTED} AND ({writable}))")


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
