from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from shared.db import APP_ALIAS, MIGRATE_ALIAS, OPERATOR_ALIAS, PRINCIPAL_SETTING

BYPASSRLS = "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"
OWNED = "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user"
UNSET = f"SELECT current_setting('{PRINCIPAL_SETTING}', true) IS NULL"


def _ask(alias, statement):
    connection = connections[alias]
    connection.close()
    with connection.cursor() as cursor:
        cursor.execute(statement)
        return cursor.fetchone()[0]


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

        if findings:
            raise CommandError(
                "The row-level-security roles are not what the policies assume:\n  " + "\n  ".join(findings)
            )

        self.stdout.write(
            f"{users[APP_ALIAS]} is scoped and owns nothing, {users[OPERATOR_ALIAS]} bypasses, "
            f"{users[MIGRATE_ALIAS]} owns the tables, and a fresh connection carries no principal."
        )
