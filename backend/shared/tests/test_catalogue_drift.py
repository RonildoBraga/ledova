import re
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from shared.db import MIGRATE_ALIAS
from shared.db.policies import HELPERS, POLICIES, MissingOwnerColumns
from shared.management.commands.check_rls_catalogue import DRIFTED

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


class CatalogueDriftDocumentationTest(SimpleTestCase):

    def test_the_drift_error_points_to_an_existing_document_heading(self):
        message = DRIFTED.format(count=1, findings="companies_company: missing read policy")
        reference = re.search(r'The rule is in (docs/[^,\s]+), "([^"]+)"\.', message)

        self.assertIsNotNone(reference, message)
        document, heading = reference.groups()
        text = (Path(settings.BASE_DIR).parent / document).read_text()

        self.assertIn(heading, re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE), document)


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

    def test_an_extra_permissive_policy_is_reported_and_preserved_after_the_probe(self):
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            cursor.execute(f'CREATE POLICY "legacy read grant" ON {A_TABLE} FOR SELECT USING (true)')
        before = what_is_installed("legacy read grant")

        with self.assertRaises(CommandError) as refused:
            call_command("check_rls_catalogue")

        self.assertIn(
            f"{A_TABLE}: legacy read grant is in the database and not in the catalogue", str(refused.exception)
        )
        self.assertEqual(what_is_installed("legacy read grant"), before)

    def test_a_policy_for_a_different_role_is_reported_even_when_its_predicate_matches(self):
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            cursor.execute(f"ALTER POLICY {A_TABLE}_read ON {A_TABLE} TO CURRENT_USER")

        with self.assertRaises(CommandError) as refused:
            call_command("check_rls_catalogue")

        self.assertIn(f"{A_TABLE}_read TO differs", str(refused.exception))
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            cursor.execute("SELECT polroles = ARRAY[0]::oid[] FROM pg_policy WHERE polname = %s", [f"{A_TABLE}_read"])
            self.assertFalse(cursor.fetchone()[0])

    def test_a_restrictive_policy_is_reported_even_when_its_predicate_matches(self):
        readable, _ = what_is_installed(f"{A_TABLE}_read")
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            cursor.execute(f"DROP POLICY {A_TABLE}_read ON {A_TABLE}")
            cursor.execute(f"CREATE POLICY {A_TABLE}_read ON {A_TABLE} AS RESTRICTIVE FOR SELECT USING ({readable})")

        with self.assertRaises(CommandError) as refused:
            call_command("check_rls_catalogue")

        self.assertIn(f"{A_TABLE}_read AS differs", str(refused.exception))
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            cursor.execute("SELECT polpermissive FROM pg_policy WHERE polname = %s", [f"{A_TABLE}_read"])
            self.assertFalse(cursor.fetchone()[0])

    def test_helper_execution_attributes_are_compared_without_rewriting_the_installed_function(self):
        for alteration, restore, clause in (
            ("VOLATILE", "STABLE", "volatility"),
            ("SECURITY DEFINER", "SECURITY INVOKER", "security"),
            ("STRICT", "CALLED ON NULL INPUT", "strictness"),
            ("PARALLEL SAFE", "PARALLEL UNSAFE", "parallel"),
        ):
            with self.subTest(clause=clause):
                with connections[MIGRATE_ALIAS].cursor() as cursor:
                    cursor.execute(f"ALTER FUNCTION {A_HELPER}() {alteration}")
                    cursor.execute("SELECT pg_get_functiondef(%s::regprocedure)", [f"{A_HELPER}()"])
                    before = cursor.fetchone()[0]
                try:
                    with self.assertRaises(CommandError) as refused:
                        call_command("check_rls_catalogue")
                    self.assertIn(f"{A_HELPER}: the {clause} differs", str(refused.exception))
                    with connections[MIGRATE_ALIAS].cursor() as cursor:
                        cursor.execute("SELECT pg_get_functiondef(%s::regprocedure)", [f"{A_HELPER}()"])
                        self.assertEqual(cursor.fetchone()[0], before)
                finally:
                    with connections[MIGRATE_ALIAS].cursor() as cursor:
                        cursor.execute(f"ALTER FUNCTION {A_HELPER}() {restore}")

    def test_a_different_helper_language_cannot_hide_behind_an_identical_body(self):
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            cursor.execute("SET LOCAL check_function_bodies = off")
            cursor.execute(
                f"CREATE OR REPLACE FUNCTION {A_HELPER}() RETURNS SETOF uuid "
                f"LANGUAGE plpgsql STABLE AS $${HELPERS[A_HELPER]}$$"
            )

        with self.assertRaises(CommandError) as refused:
            call_command("check_rls_catalogue")

        self.assertIn(f"{A_HELPER}: the language differs", str(refused.exception))

    def test_an_ownership_column_that_is_already_required_cannot_stay_on_the_wait_list(self):
        waiting = {
            "tokens_capitalincreaserequest": MissingOwnerColumns(("company_id",), "Waiting for company ownership"),
            "tokens_shareissuancerequest": MissingOwnerColumns(("company_id",), "Waiting for company ownership"),
        }
        with patch("shared.management.commands.check_rls_catalogue.AWAITING_R0", waiting, create=True):
            with self.assertRaises(CommandError) as refused:
                call_command("check_rls_catalogue")

        for table in waiting:
            self.assertIn(f"{table}.company_id is already NOT NULL", str(refused.exception))

    def test_absent_and_nullable_columns_remain_valid_ownership_prerequisites(self):
        for column in ("not_yet_added_id", "reviewed_by_id"):
            with self.subTest(column=column):
                waiting = {
                    "tokens_capitalincreaserequest": MissingOwnerColumns((column,), "Waiting for an owner column")
                }
                with patch("shared.management.commands.check_rls_catalogue.AWAITING_R0", waiting, create=True):
                    call_command("check_rls_catalogue")


@skipUnless(POSTGRES, REASON)
class ReviewRequestPolicyMigrationTest(TransactionTestCase):
    def migrate_to(self, target):
        MigrationExecutor(connections[MIGRATE_ALIAS]).migrate(target)

    def test_an_existing_installation_gains_the_request_policies_without_losing_them_on_reversal(self):
        latest = MigrationExecutor(connections[MIGRATE_ALIAS]).loader.graph.leaf_nodes()
        self.addCleanup(self.migrate_to, latest)
        self.migrate_to([("shared", "0006_account_insert_by_director")])
        with connections[MIGRATE_ALIAS].cursor() as cursor:
            for table in ("tokens_capitalincreaserequest", "tokens_shareissuancerequest"):
                for suffix in ("read", "insert", "update", "delete"):
                    cursor.execute(f"DROP POLICY {table}_{suffix} ON {table}")
                cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
                cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")

        with self.assertRaises(CommandError):
            call_command("check_rls_catalogue")

        self.migrate_to([("shared", "0007_review_request_policies")])
        call_command("check_rls_catalogue")

        self.migrate_to([("shared", "0006_account_insert_by_director")])
        call_command("check_rls_catalogue")
