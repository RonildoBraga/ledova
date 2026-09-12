import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connections

from shared.db import APP_ALIAS, MIGRATE_ALIAS, OPERATOR_ALIAS, PRINCIPAL_SETTING
from shared.db.policy_sql import reachable_by_the_app_role

BYPASSRLS = "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"
OWNED = "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user"
UNSET = f"SELECT current_setting('{PRINCIPAL_SETTING}', true) IS NULL"
REACHED = """
SELECT coalesce(json_agg(c.relname ORDER BY c.relname), '[]')::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND has_table_privilege(current_user, c.oid, 'SELECT')
"""


CANNOT_AUTHENTICATE = (
    "{alias} cannot connect as {user}: {error}"
    "\n    shared/0003 creates that role with LOGIN and no password, on purpose - a credential does "
    "not belong in a migration - so the server has to be one that admits it."
    "\n    A cluster initialised without POSTGRES_HOST_AUTH_METHOD=trust uses scram-sha-256 over "
    "anything but loopback, and refuses every passwordless role."
    "\n    On a new database: set POSTGRES_HOST_AUTH_METHOD=trust, which docker-compose.yml now does."
    "\n    On one that already exists initdb has already written pg_hba.conf, so give the role the "
    "password the settings expect instead:"
    "\n      ALTER ROLE {user} LOGIN PASSWORD '<the POSTGRES_PASSWORD in backend/.env>';"
    "\n    Or set {prefix}_PASSWORD to whatever the role's password already is."
)


REFUSED_CREDENTIALS = ("password authentication failed", "no password supplied", "authentication failed")

CANNOT_CONNECT = "{alias} cannot connect as {user}: {cause}"


def _causal_line(error) -> str:
    return str(error).strip().splitlines()[0]


def _is_a_refused_credential(error) -> bool:
    said = str(error).lower()
    return any(phrase in said for phrase in REFUSED_CREDENTIALS)


def _ask(alias, statement):
    connection = connections[alias]
    connection.close()
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement)
            return cursor.fetchone()[0]
    except OperationalError as error:
        cause = _causal_line(error)
        user = settings.DATABASES[alias]["USER"]
        if not _is_a_refused_credential(error):
            raise CommandError(CANNOT_CONNECT.format(alias=alias, user=user, cause=cause)) from error
        raise CommandError(
            CANNOT_AUTHENTICATE.format(
                alias=alias,
                user=user,
                error=cause,
                prefix="RLS_APP_DB" if alias == APP_ALIAS else "RLS_OPERATOR_DB",
            )
        ) from error


class Command(BaseCommand):
    help = "Assert the row-level-security role plumbing that no test can see."

    def handle(self, *args, **options):
        missing = [alias for alias in (APP_ALIAS, OPERATOR_ALIAS, MIGRATE_ALIAS) if alias not in settings.DATABASES]
        if missing:
            raise CommandError(
                f"DATABASES has no {', '.join(missing)} alias, so the roles this checks for cannot be "
                "reached. Run it against a deployment that configures all three."
            )

        users = {alias: settings.DATABASES[alias]["USER"] for alias in (APP_ALIAS, OPERATOR_ALIAS, MIGRATE_ALIAS)}
        findings = []

        if len(set(users.values())) != 3:
            findings.append(f"the three aliases must log in as three different roles, and they are {users}")

        if _ask(APP_ALIAS, BYPASSRLS):
            findings.append(f"{users[APP_ALIAS]} has BYPASSRLS, so every policy on every table is decoration")

        owned = _ask(APP_ALIAS, OWNED)
        if owned:
            findings.append(
                f"{users[APP_ALIAS]} owns {owned} table(s) in public, and FORCE ROW LEVEL SECURITY is the "
                "only thing that would scope an owner, so it must own none"
            )

        if not _ask(OPERATOR_ALIAS, BYPASSRLS):
            findings.append(
                f"{users[OPERATOR_ALIAS]} has no BYPASSRLS, so the admin, the workers and the commands "
                "are scoped to a principal none of them has"
            )

        if not _ask(MIGRATE_ALIAS, OWNED):
            findings.append(f"{users[MIGRATE_ALIAS]} owns no table in public, so it did not run the migrations")

        if not _ask(APP_ALIAS, UNSET):
            findings.append(
                f"a fresh {users[APP_ALIAS]} connection already carries {PRINCIPAL_SETTING}, so a principal "
                "is surviving between requests and one caller can read another's rows"
            )

        reached = set(json.loads(_ask(APP_ALIAS, REACHED)))
        catalogued = set(reachable_by_the_app_role())
        beyond = sorted(reached - catalogued)
        short = sorted(catalogued - reached)
        if beyond:
            findings.append(
                f"{users[APP_ALIAS]} can read {', '.join(beyond)}, which the catalogue does not list as "
                "reachable. A table nobody classified must not be readable by the scoped role."
            )
        if short:
            findings.append(
                f"{users[APP_ALIAS]} cannot read {', '.join(short)}, which the catalogue says it reaches. "
                "The grant migration ran before those tables existed, or a later migration created them "
                "under the default privileges that now deny it."
            )

        if findings:
            raise CommandError(
                "The row-level-security roles are not what the policies assume:\n  " + "\n  ".join(findings)
            )

        self.stdout.write(
            f"{users[APP_ALIAS]} is scoped, owns nothing and reaches exactly the {len(reached)} tables "
            f"the catalogue lists, {users[OPERATOR_ALIAS]} bypasses, {users[MIGRATE_ALIAS]} owns the "
            "tables, and a fresh connection carries no principal."
        )
