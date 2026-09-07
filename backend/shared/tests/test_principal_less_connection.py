from unittest import skipUnless

import psycopg
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from shared.db.principal import PRINCIPAL_SETTING

POSTGRES = connection.vendor == "postgresql"
REASON = "row-level security exists only in PostgreSQL, and on SQLite this would pass with no policy at all"

POLICIED = "companies_company"
ASK = f"SELECT count(*) FROM {POLICIED}"
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
        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
                cursor.execute(ASK)

                self.assertEqual(cursor.fetchone()[0], 0)

    def test_the_missing_principal_is_null_rather_than_a_parameter_the_server_refuses(self):
        with self.a_session_that_has_never_set_the_principal() as fresh:
            with fresh.cursor() as cursor:
                cursor.execute(f"SELECT current_setting('{PRINCIPAL_SETTING}', true)::bigint IS NULL")

                self.assertTrue(cursor.fetchone()[0])
