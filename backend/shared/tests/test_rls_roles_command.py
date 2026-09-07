from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, override_settings

from shared.db import APP_ALIAS, MIGRATE_ALIAS, OPERATOR_ALIAS

REFUSED = 'connection failed: FATAL:  password authentication failed for user "ledova_app"'
CONNECTIONS = "shared.management.commands.check_rls_roles.connections"

THREE_ALIASES = {
    MIGRATE_ALIAS: {"USER": "ledova", "ENGINE": "django.db.backends.postgresql", "NAME": "ledova"},
    APP_ALIAS: {"USER": "ledova_app", "ENGINE": "django.db.backends.postgresql", "NAME": "ledova"},
    OPERATOR_ALIAS: {"USER": "ledova_operator", "ENGINE": "django.db.backends.postgresql", "NAME": "ledova"},
}


@override_settings(DATABASES=THREE_ALIASES)
class ARefusedConnectionSaysWhatToDoAboutIt(SimpleTestCase):

    def _refused(self, alias):
        def connection_for(asked_alias):
            connection = MagicMock()
            if asked_alias == alias:
                connection.cursor.side_effect = OperationalError(REFUSED)
            else:
                connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (False,)
            return connection

        connections = MagicMock()
        connections.__getitem__.side_effect = connection_for
        return connections

    def test_the_message_names_the_role_the_migration_left_without_a_password(self):
        with patch(CONNECTIONS, self._refused(APP_ALIAS)):
            with self.assertRaises(CommandError) as refusal:
                call_command("check_rls_roles")

        self.assertIn("ledova_app", str(refusal.exception))
        self.assertIn("LOGIN and no password", str(refusal.exception))

    def test_the_message_names_both_remedies_and_which_database_each_is_for(self):
        with patch(CONNECTIONS, self._refused(APP_ALIAS)):
            with self.assertRaises(CommandError) as refusal:
                call_command("check_rls_roles")

        message = str(refusal.exception)
        self.assertIn("POSTGRES_HOST_AUTH_METHOD=trust", message)
        self.assertIn("ALTER ROLE ledova_app LOGIN PASSWORD", message)
        self.assertIn("RLS_APP_DB_PASSWORD", message)

    def test_the_operator_alias_is_told_to_set_its_own_variable_not_the_app_one(self):
        with patch(CONNECTIONS, self._refused(OPERATOR_ALIAS)):
            with self.assertRaises(CommandError) as refusal:
                call_command("check_rls_roles")

        message = str(refusal.exception)
        self.assertIn("ALTER ROLE ledova_operator LOGIN PASSWORD", message)
        self.assertIn("RLS_OPERATOR_DB_PASSWORD", message)
        self.assertNotIn("RLS_APP_DB_PASSWORD", message)

    def test_the_servers_own_words_are_carried_rather_than_replaced(self):
        with patch(CONNECTIONS, self._refused(APP_ALIAS)):
            with self.assertRaises(CommandError) as refusal:
                call_command("check_rls_roles")

        self.assertIn("password authentication failed", str(refusal.exception))
