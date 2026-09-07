from unittest import skipUnless

from django.apps import apps
from django.db import connection
from django.test import TransactionTestCase

from shared.db.policies import (
    AWAITING_R0,
    DERIVED_FROM_A_MUTABLE_ATTRIBUTE,
    HELPERS,
    LEAF_TABLES,
    POLICIES,
    UNSCOPED,
)

POSTGRES = connection.vendor == "postgresql"
REASON = "row-level security exists only in PostgreSQL, and on SQLite these would pass without a policy"

SCOPED = "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s AND relkind = 'r'"
POLICY_EXPRESSIONS = (
    "SELECT policyname, qual, with_check FROM pg_policies WHERE schemaname = 'public' AND tablename = %s"
)

NEGATIONS = (" not in ", "<>", "!=", " is distinct from ")


def model_tables():
    return {model._meta.db_table for model in apps.get_models()} | {
        field.remote_field.through._meta.db_table
        for model in apps.get_models()
        for field in model._meta.local_many_to_many
    }


@skipUnless(POSTGRES, REASON)
class EveryTenantTableIsScopedByAPolicyTest(TransactionTestCase):

    def _ask(self, statement, table):
        with connection.cursor() as cursor:
            cursor.execute(statement, [table])
            return cursor.fetchall()

    def test_every_catalogued_table_has_row_level_security_enabled_and_forced(self):
        for table in sorted(POLICIES):
            with self.subTest(table=table):
                rows = self._ask(SCOPED, table)
                self.assertEqual(rows, [(True, True)], f"{table} carries a policy that nothing turns on")

    def test_every_catalogued_table_has_at_least_one_policy(self):
        for table in sorted(POLICIES):
            with self.subTest(table=table):
                self.assertNotEqual(self._ask(POLICY_EXPRESSIONS, table), [])

    def test_every_table_in_the_application_is_classified(self):
        classified = set(POLICIES) | set(AWAITING_R0) | set(UNSCOPED)

        self.assertEqual(sorted(model_tables() - classified), [])

    def test_no_classification_names_a_table_that_does_not_exist(self):
        classified = set(POLICIES) | set(AWAITING_R0) | set(UNSCOPED)

        self.assertEqual(sorted(classified - model_tables()), [])

    def test_an_unclassified_table_would_be_reported_rather_than_ignored(self):
        classified = (set(POLICIES) | set(AWAITING_R0) | set(UNSCOPED)) - {"wallets"}

        self.assertEqual(sorted(model_tables() - classified), ["wallets"])

    def test_a_row_that_can_be_read_can_be_locked(self):
        for table in sorted(POLICIES):
            with self.subTest(table=table):
                policies = {name: qual for name, qual, _ in self._ask(POLICY_EXPRESSIONS, table)}

                self.assertEqual(
                    policies[f"{table}_update"],
                    policies[f"{table}_read"],
                    "PostgreSQL applies the UPDATE policy's USING to SELECT ... FOR UPDATE, so a row the "
                    "read policy admits and the update policy does not can be read and never locked - and "
                    "select_for_update().get() turns that into DoesNotExist. USING is the read scope; the "
                    "narrowing belongs in WITH CHECK.",
                )

    def test_the_update_policy_still_narrows_what_may_be_written(self):
        for table in sorted(POLICIES):
            with self.subTest(table=table):
                policies = {name: check for name, _, check in self._ask(POLICY_EXPRESSIONS, table)}

                self.assertEqual(policies[f"{table}_update"], policies[f"{table}_insert"])

    def test_the_membership_tables_carry_leaf_policies(self):
        for table in LEAF_TABLES:
            with self.subTest(table=table):
                for _, qual, check in self._ask(POLICY_EXPRESSIONS, table):
                    self.assertNotIn("app_", qual or "")
                    self.assertNotIn("app_", check or "")

    def test_no_tenancy_predicate_is_written_as_a_negation(self):
        for table in sorted(POLICIES):
            with self.subTest(table=table):
                for _, qual, check in self._ask(POLICY_EXPRESSIONS, table):
                    for expression in (qual or "", check or ""):
                        for negation in NEGATIONS:
                            self.assertNotIn(negation, expression.lower())

    def test_every_table_awaiting_a_column_says_which_one_and_why(self):
        for table, reason in AWAITING_R0.items():
            with self.subTest(table=table):
                self.assertGreater(len(reason), 80)
                self.assertEqual(self._ask(SCOPED, table), [(False, False)])

    def test_every_column_derived_from_a_mutable_attribute_names_what_goes_stale(self):
        for column, reason in DERIVED_FROM_A_MUTABLE_ATTRIBUTE.items():
            with self.subTest(column=column):
                table, _, _ = column.partition(".")
                self.assertIn(table, set(POLICIES) | set(AWAITING_R0))
                self.assertGreater(len(reason), 150, f"{column} needs the staleness named, not flagged")

    def test_every_unscoped_table_states_a_reason_rather_than_a_label(self):
        for table, reason in UNSCOPED.items():
            with self.subTest(table=table):
                self.assertGreater(len(reason), 20)

    def test_the_helpers_exist_and_are_stable_rather_than_security_definer(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT proname, provolatile, prosecdef FROM pg_proc WHERE proname = ANY(%s) ORDER BY proname",
                [sorted(HELPERS)],
            )
            rows = cursor.fetchall()

        self.assertEqual([name for name, _, _ in rows], sorted(HELPERS))
        for name, volatility, definer in rows:
            with self.subTest(helper=name):
                self.assertEqual(volatility, "s")
                self.assertFalse(definer)
