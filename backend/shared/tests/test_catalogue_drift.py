from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import TestCase

from shared.db import MIGRATE_ALIAS
from shared.db.policies import HELPERS, POLICIES

POSTGRES = connections[MIGRATE_ALIAS].vendor == "postgresql"
REASON = (
    "the policies are a PostgreSQL feature, so on SQLite there is nothing installed for the "
    "catalogue to differ from and this would report the same green either way"
)

INSTALLED = (
    "SELECT pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid) FROM pg_policy WHERE polname = %s"
)

A_TABLE = "companies_company"
A_HELPER = "app_public_company_ids"


def a_catalogue_with(table, readable):
    changed = dict(POLICIES)
    changed[table] = (readable, POLICIES[table][1])
    return changed


def what_is_installed(policy):
    with connections[MIGRATE_ALIAS].cursor() as cursor:
        cursor.execute(INSTALLED, [policy])
        return cursor.fetchone()


@skipUnless(POSTGRES, REASON)
class TheCatalogueMatchesWhatIsInstalledTest(TestCase):

    def test_a_database_migrated_from_the_catalogue_agrees_with_it(self):
        call_command("check_rls_catalogue")

    def test_a_changed_predicate_names_its_table_its_policy_and_its_clause(self):
        with patch("shared.db.policy_sql.POLICIES", a_catalogue_with(A_TABLE, "owner_id IS NOT NULL")):
            with self.assertRaises(CommandError) as refused:
                call_command("check_rls_catalogue")

        said = str(refused.exception)
        self.assertIn(f"{A_TABLE}: {A_TABLE}_read USING differs", said)
        self.assertIn("owner_id IS NOT NULL", said)
        self.assertIn("database:", said)
        self.assertIn("catalogue:", said)

    def test_the_update_policy_carries_both_clauses_and_each_is_named_on_its_own(self):
        with patch("shared.db.policy_sql.POLICIES", a_catalogue_with(A_TABLE, "owner_id IS NOT NULL")):
            with self.assertRaises(CommandError) as refused:
                call_command("check_rls_catalogue")

        said = str(refused.exception)
        self.assertIn(f"{A_TABLE}_update USING differs", said)
        self.assertNotIn(f"{A_TABLE}_update WITH CHECK differs", said)

    def test_a_changed_helper_body_is_named(self):
        changed = dict(HELPERS)
        changed[A_HELPER] = "SELECT uuid FROM companies_company WHERE owner_id IS NOT NULL"

        with patch("shared.db.policy_sql.HELPERS", changed):
            with self.assertRaises(CommandError) as refused:
                call_command("check_rls_catalogue")

        self.assertIn(f"{A_HELPER}: the body differs", str(refused.exception))

    def test_a_catalogue_that_will_not_install_says_so_rather_than_raising_the_driver_error(self):
        with patch("shared.db.policy_sql.POLICIES", a_catalogue_with(A_TABLE, "no_such_column IS NOT NULL")):
            with self.assertRaises(CommandError) as refused:
                call_command("check_rls_catalogue")

        said = str(refused.exception)
        self.assertIn("the catalogue does not install against this database", said)
        self.assertIn('column "no_such_column" does not exist', said)

    def test_the_probe_leaves_every_installed_policy_exactly_as_it_found_it(self):
        before = {name: what_is_installed(name) for name in (f"{A_TABLE}_read", f"{A_TABLE}_update")}

        with patch("shared.db.policy_sql.POLICIES", a_catalogue_with(A_TABLE, "owner_id IS NOT NULL")):
            with self.assertRaises(CommandError):
                call_command("check_rls_catalogue")

        self.assertEqual({name: what_is_installed(name) for name in before}, before)

    def test_it_counts_what_it_compared_rather_than_only_saying_it_passed(self):
        with patch("sys.stdout") as printed:
            call_command("check_rls_catalogue")

        said = "".join(str(call) for call in printed.write.call_args_list)
        self.assertIn(f"{len(POLICIES) * 4} policies across {len(POLICIES)} tables", said)
        self.assertIn(f"{len(HELPERS)} helpers", said)
