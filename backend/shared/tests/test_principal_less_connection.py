from unittest import skipUnless

import psycopg
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from shared.db.policies import PRINCIPAL
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.tenants import make_tenant

POSTGRES = connection.vendor == "postgresql"
REASON = "row-level security exists only in PostgreSQL, and on SQLite this would pass with no policy at all"

POLICIED = "users_userpreferences"
ASK = f"SELECT count(*) FROM {POLICIED}"
WIDENED = "SELECT count(*) FROM companies_company"
LISTED = "UPDATE companies_company SET status = 'active', is_open_to_investors = true"
DEFINED = f"SELECT current_setting('{PRINCIPAL_SETTING}', true) IS NOT NULL"


@skipUnless(POSTGRES, REASON)
class AConnectionThatNeverSetAPrincipalSeesNothingRatherThanFailingTest(TransactionTestCase):

    def a_session_that_has_never_set_the_principal(self):
        parameters = connection.get_connection_params()
        parameters.pop("cursor_factory", None)
        parameters.pop("context", None)
        fresh = psycopg.connect(**parameters)
        self.addCleanup(fresh.close)
        return fresh

    def test_the_setting_really_is_undefined_so_the_assertion_below_means_something(self):
        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(DEFINED)

                self.assertFalse(cursor.fetchone()[0], "the fixture set the principal, so nothing here is tested")

    def test_the_app_role_reads_a_policied_table_and_gets_no_rows_instead_of_an_error(self):
        make_tenant("principalless")

        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(ASK)
                self.assertGreater(cursor.fetchone()[0], 0, "no rows to hide, so a zero below proves nothing")

                cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
                cursor.execute(ASK)

                self.assertEqual(cursor.fetchone()[0], 0)

    def test_the_missing_principal_is_null_rather_than_a_parameter_the_server_refuses(self):
        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(f"SELECT {PRINCIPAL} IS NULL")

                self.assertTrue(cursor.fetchone()[0])

    def test_a_principal_that_was_set_and_then_cleared_reads_as_absent_rather_than_as_empty(self):
        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, "7"])
                cursor.execute(f"SELECT {PRINCIPAL}")
                self.assertEqual(cursor.fetchone()[0], 7)

                cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])
                cursor.execute(f"SELECT {PRINCIPAL} IS NULL")

                self.assertTrue(cursor.fetchone()[0])

    def test_the_app_role_reads_nothing_after_a_principal_is_cleared_rather_than_failing(self):
        make_tenant("clearedprincipal")

        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
                cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, "7"])
                cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])
                cursor.execute(ASK)

                self.assertEqual(cursor.fetchone()[0], 0)

    def test_a_widened_policy_admits_nobody_when_no_principal_was_named(self):
        make_tenant("widenedpolicy")

        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(LISTED)
                fresh.commit()
                cursor.execute(WIDENED)
                self.assertGreater(cursor.fetchone()[0], 0, "no public row to admit, so a zero below proves nothing")

                cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
                cursor.execute(WIDENED)

                self.assertEqual(cursor.fetchone()[0], 0)
