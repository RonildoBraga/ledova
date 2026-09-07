from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, connections
from rest_framework.test import APITransactionTestCase

from shared.db import APP_ALIAS, PRINCIPAL_SETTING, current_alias
from shared.tests.scoped import RunsOnTheScopedConnection

User = get_user_model()


class TheScopedHarnessIsActuallyScopedTest(RunsOnTheScopedConnection, APITransactionTestCase):

    def test_the_ambient_alias_is_the_scoped_one_and_not_the_migrate_one(self):
        self.assertEqual(settings.RLS_AMBIENT_ALIAS, APP_ALIAS)
        self.assertEqual(current_alias(), APP_ALIAS)

    def test_the_queries_really_reach_the_scoped_role(self):
        with connections[current_alias()].cursor() as cursor:
            cursor.execute("SELECT current_user")

            self.assertEqual(cursor.fetchone()[0], settings.RLS_ROLES[APP_ALIAS])

    def test_a_fixture_written_as_an_operator_is_visible_to_the_principal_it_belongs_to(self):
        with self.as_an_operator_would():
            user = User.objects.create_user(email="harness@example.test", password="pw-12345678", is_active=True)
        self.signed_in_as(user)

        with connections[current_alias()].cursor() as cursor:
            cursor.execute(f"SELECT current_setting('{PRINCIPAL_SETTING}', true)::bigint")

            self.assertEqual(cursor.fetchone()[0], user.pk)

    def test_without_a_principal_the_same_connection_carries_none(self):
        self.no_principal_is_set()

        with connections[current_alias()].cursor() as cursor:
            cursor.execute(f"SELECT NULLIF(current_setting('{PRINCIPAL_SETTING}', true), '') IS NULL")

            self.assertTrue(cursor.fetchone()[0])

    def test_the_default_connection_is_not_the_one_the_queries_use(self):
        self.assertNotEqual(current_alias(), "default")
        self.assertIs(connections[current_alias()], connections[APP_ALIAS])
        self.assertIsNot(connections[current_alias()], connection)
