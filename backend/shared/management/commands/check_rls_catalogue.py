from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections

from shared.db import MIGRATE_ALIAS, atomic
from shared.db.policies import AWAITING_R0, HELPERS, POLICIES
from shared.db.policy_sql import install

POLICY_STATE = """
    SELECT c.relname, p.polname, p.polcmd,
           coalesce(pg_get_expr(p.polqual, p.polrelid), ''),
           coalesce(pg_get_expr(p.polwithcheck, p.polrelid), ''),
           ARRAY(SELECT CASE WHEN role_oid = 0 THEN 'PUBLIC'
                             ELSE pg_get_userbyid(role_oid)::text END
                   FROM unnest(p.polroles) role_oid ORDER BY 1),
           CASE WHEN p.polpermissive THEN 'PERMISSIVE' ELSE 'RESTRICTIVE' END
      FROM pg_policy p
      JOIN pg_class c ON c.oid = p.polrelid
     WHERE c.relnamespace = 'public'::regnamespace AND c.relname = ANY(%s)
"""

RELATION_STATE = """
    SELECT relname, relrowsecurity, relforcerowsecurity
      FROM pg_class
     WHERE relnamespace = 'public'::regnamespace AND relname = ANY(%s)
"""

HELPER_STATE = """
    SELECT p.proname, p.prosrc, l.lanname, p.provolatile, p.prosecdef,
           p.proisstrict, p.proparallel, p.proleakproof, p.proconfig,
           pg_get_function_result(p.oid)
      FROM pg_proc p
      JOIN pg_language l ON l.oid = p.prolang
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = ANY(%s) AND p.pronargs = 0
"""

HELPER_CLAUSES = (
    "body",
    "language",
    "volatility",
    "security",
    "strictness",
    "parallel",
    "leakproof",
    "configuration",
    "result",
)

REQUIRED_COLUMNS = """
    SELECT a.attname
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
     WHERE c.relnamespace = 'public'::regnamespace AND c.relname = %s
       AND a.attname = ANY(%s) AND a.attnotnull AND NOT a.attisdropped AND a.attnum > 0
"""

NOT_POSTGRES = (
    "{alias} is {vendor}, and row-level security is a PostgreSQL feature, so there is nothing "
    "installed to compare the catalogue against. Run this against the database the deployment uses."
)

MISSING_TABLE = "{table}: the catalogue names it, and public has no such table"
RLS_OFF = "{table}: the catalogue policies it, and ROW LEVEL SECURITY is {state} on the table"
POLICY_MISSING = "{table}: {policy} is in the catalogue and not in the database"
POLICY_EXTRA = "{table}: {policy} is in the database and not in the catalogue"
POLICY_DIFFERS = "{table}: {policy} {clause} differs\n      database:  {installed}\n      catalogue: {rendered}"
WILL_NOT_INSTALL = (
    "the catalogue does not install against this database, so no fresh database could be built from "
    "it either, and there is nothing to compare:\n      {error}"
)
HELPER_MISSING = "{helper}: the catalogue defines it, and public has no such function"
HELPER_DIFFERS = "{helper}: the {clause} differs\n      database:  {installed}\n      catalogue: {rendered}"

DRIFTED = (
    "The database has policies the catalogue no longer describes ({count}):\n\n  {findings}\n\n"
    "shared/db/policies.py is read at migration time, so a change to it alters what a fresh "
    "database gets while every existing database keeps what it was given. Both work; they are "
    "simply different, and the difference surfaces as a defect on one deployment and not another.\n"
    "Add a migration that re-runs shared.db.policy_sql.install, then run this again.\n"
    'The rule is in docs/ARCHITECTURE.md, "The catalogue is read at migration time".'
)

AGREES = (
    "The installed policies and helpers are the ones the catalogue describes: "
    "{policies} policies across {tables} tables, and {helpers} helpers."
)


class Rolled(Exception):

    def __init__(self, state):
        super().__init__("the probe install is rolled back and its reading carried out with it")
        self.state = state


def state_of(cursor, tables, helpers):
    cursor.execute(POLICY_STATE, [tables])
    policies = {(table, name): tuple(attributes) for table, name, *attributes in cursor.fetchall()}
    cursor.execute(RELATION_STATE, [tables])
    relations = {table: (enabled, forced) for table, enabled, forced in cursor.fetchall()}
    cursor.execute(HELPER_STATE, [helpers])
    functions = {name: tuple(attributes) for name, *attributes in cursor.fetchall()}
    return policies, relations, functions


def would_be_installed(owner, tables, helpers):
    try:
        with atomic(owner.alias):
            with owner.cursor() as cursor:
                cursor.execute("SET LOCAL search_path = public, pg_catalog")
                cursor.execute(POLICY_STATE, [tables])
                existing = cursor.fetchall()
                quote = owner.ops.quote_name
                for table, name, *_ in existing:
                    cursor.execute(f"DROP POLICY {quote(name)} ON {quote('public')}.{quote(table)}")
            with owner.schema_editor(atomic=False) as editor:
                install(editor)
            with owner.cursor() as cursor:
                raise Rolled(state_of(cursor, tables, helpers))
    except Rolled as probe:
        return probe.state
    except DatabaseError as refused:
        raise CommandError(
            DRIFTED.format(count=1, findings=WILL_NOT_INSTALL.format(error=str(refused).strip().splitlines()[0]))
        ) from refused


def policy_findings(installed, rendered):
    findings = []
    for key in sorted(rendered.keys() - installed.keys()):
        findings.append(POLICY_MISSING.format(table=key[0], policy=key[1]))
    for key in sorted(installed.keys() - rendered.keys()):
        findings.append(POLICY_EXTRA.format(table=key[0], policy=key[1]))
    for key in sorted(installed.keys() & rendered.keys()):
        was, now = installed[key], rendered[key]
        for index, clause in enumerate(("FOR", "USING", "WITH CHECK", "TO", "AS")):
            if was[index] != now[index]:
                findings.append(
                    POLICY_DIFFERS.format(
                        table=key[0], policy=key[1], clause=clause, installed=was[index], rendered=now[index]
                    )
                )
    return findings


def relation_findings(relations, tables):
    findings = []
    for table in tables:
        if table not in relations:
            findings.append(MISSING_TABLE.format(table=table))
            continue
        enabled, forced = relations[table]
        if not enabled:
            findings.append(RLS_OFF.format(table=table, state="disabled"))
        elif not forced:
            findings.append(RLS_OFF.format(table=table, state="enabled but not forced, so the owner is unscoped"))
    return findings


def helper_findings(installed, rendered):
    findings = []
    for helper in sorted(rendered):
        if helper not in installed:
            findings.append(HELPER_MISSING.format(helper=helper))
            continue
        for index, clause in enumerate(HELPER_CLAUSES):
            was, now = installed[helper][index], rendered[helper][index]
            if was != now:
                findings.append(
                    HELPER_DIFFERS.format(
                        helper=helper,
                        clause=clause,
                        installed=" ".join(str(was).split()),
                        rendered=" ".join(str(now).split()),
                    )
                )
    return findings


def ownership_wait_findings(cursor, waiting):
    findings = []
    for table, prerequisite in sorted(waiting.items()):
        if not prerequisite.columns:
            findings.append(f"{table}: AWAITING_R0 must name the ownership columns that are still missing")
            continue
        cursor.execute(REQUIRED_COLUMNS, [table, list(prerequisite.columns)])
        for (column,) in cursor.fetchall():
            findings.append(
                f"{table}.{column} is already NOT NULL; remove the stale AWAITING_R0 prerequisite "
                "and install the policy or record the actual remaining work"
            )
    return findings


class Command(BaseCommand):
    help = "Assert the installed policies and helpers are the ones shared/db/policies.py describes."

    def handle(self, *args, **options):
        owner = connections[MIGRATE_ALIAS]
        if owner.vendor != "postgresql":
            raise CommandError(NOT_POSTGRES.format(alias=MIGRATE_ALIAS, vendor=owner.vendor))

        tables, helpers = sorted(POLICIES), sorted(HELPERS)
        with owner.cursor() as cursor:
            installed, relations, functions = state_of(cursor, tables, helpers)
            ownership_waits = ownership_wait_findings(cursor, AWAITING_R0)
        rendered, _, would_be = would_be_installed(owner, tables, helpers)

        findings = (
            ownership_waits
            + relation_findings(relations, tables)
            + policy_findings(installed, rendered)
            + helper_findings(functions, would_be)
        )

        if findings:
            raise CommandError(DRIFTED.format(count=len(findings), findings="\n  ".join(findings)))

        self.stdout.write(
            AGREES.format(policies=len(installed), tables=len(tables), helpers=len(functions)),
        )
