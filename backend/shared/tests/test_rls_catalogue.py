import importlib.util
from pathlib import Path
from unittest import skipUnless

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from shared.db.policies import (
    AWAITING_R0,
    BYPASSES_VISIBLE_TO_USER,
    DERIVED_FROM_A_MUTABLE_ATTRIBUTE,
    HELPERS,
    INSERTABLE,
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

LAYER_GATE = Path(settings.BASE_DIR).parent / "scripts" / "check-layers.py"


def views_the_gate_counts():
    spec = importlib.util.spec_from_file_location("check_layers_for_the_audit", LAYER_GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    counted = set(gate.LEGACY) | set(gate.ALLOWED)
    suffix = f":{gate.VIEW_ORM}"
    return sorted(key[len("backend/") : -len(suffix)] for key in counted if key.endswith(suffix) and "/views/" in key)


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
        for table in sorted(set(POLICIES) - set(INSERTABLE)):
            with self.subTest(table=table):
                policies = {name: check for name, _, check in self._ask(POLICY_EXPRESSIONS, table)}

                self.assertEqual(policies[f"{table}_update"], policies[f"{table}_insert"])

    def test_what_may_be_updated_is_what_may_be_deleted_because_both_are_the_writable_term(self):
        for table in sorted(POLICIES):
            with self.subTest(table=table):
                checks = {name: check for name, _, check in self._ask(POLICY_EXPRESSIONS, table)}
                quals = {name: qual for name, qual, _ in self._ask(POLICY_EXPRESSIONS, table)}

                self.assertEqual(checks[f"{table}_update"], quals[f"{table}_delete"])

    def test_an_insert_only_override_moves_insert_alone(self):
        for table in sorted(INSERTABLE):
            with self.subTest(table=table):
                checks = {name: check for name, _, check in self._ask(POLICY_EXPRESSIONS, table)}

                self.assertNotEqual(checks[f"{table}_insert"], checks[f"{table}_update"])

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
        for table, prerequisite in AWAITING_R0.items():
            with self.subTest(table=table):
                self.assertTrue(prerequisite.columns)
                self.assertGreater(len(prerequisite.reason), 80)
                self.assertEqual(self._ask(SCOPED, table), [(False, False)])

    def test_every_deliberate_bypass_names_its_call_site_term_and_proof(self):
        for name, entry in BYPASSES_VISIBLE_TO_USER.items():
            with self.subTest(read=name):
                site, term, proof = entry
                self.assertGreater(len(site), 10, f"{name} must name where it is read")
                self.assertGreater(len(term), 40, f"{name} must name the term that admits its rows")
                self.assertGreater(len(proof), 40, f"{name} must name the fixture row that proves it")

    def test_the_derived_list_is_not_empty_so_the_assertion_discriminates(self):
        views = views_the_gate_counts()

        self.assertGreater(len(views), 4)
        self.assertIn("assets/views/asset.py", views)

    def test_the_audit_covers_every_view_the_layer_gate_counts_as_reaching_the_orm(self):
        named = " ".join(site for site, _, _ in BYPASSES_VISIBLE_TO_USER.values())

        for path in views_the_gate_counts():
            with self.subTest(view=path):
                self.assertIn(path, named, f"{path} reaches the ORM in a view and the audit does not say why")

    def test_the_two_services_that_read_past_the_scope_are_named(self):
        named = " ".join(site for site, _, _ in BYPASSES_VISIBLE_TO_USER.values())

        for site in ("users/services/eligibility.py", "tokens/services/trading_order_cancel.py"):
            with self.subTest(site=site):
                self.assertIn(site, named)

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
