from unittest import skipIf, skipUnless

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase

from shared.tests.schema import (
    app_tip,
    migrate_to,
    restore_every_migration,
    unapplied_migrations,
)

TOKENS_BEFORE_OFFERINGS = [("tokens", "0014_settlement_asset_columns")]
OFFERINGS_TABLE = "offerings_offering"
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


def tables():
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class ARollbackIsRestoredForEveryAppItTouchedTest(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.addCleanup(restore_every_migration)

    def test_rolling_tokens_back_takes_offerings_with_it(self):
        self.assertIn(OFFERINGS_TABLE, tables())

        migrate_to(TOKENS_BEFORE_OFFERINGS)

        self.assertNotIn(OFFERINGS_TABLE, tables())

    def test_restoring_only_the_rolled_back_app_leaves_the_other_one_behind(self):
        migrate_to(TOKENS_BEFORE_OFFERINGS)

        migrate_to(app_tip("tokens"))

        left = unapplied_migrations()
        self.assertEqual([name for name in left if name.startswith("tokens.")], [], left)
        self.assertNotEqual([name for name in left if name.startswith("offerings.")], [], left)
        self.assertNotIn(OFFERINGS_TABLE, tables())

    def test_restoring_every_migration_puts_the_other_app_back(self):
        migrate_to(TOKENS_BEFORE_OFFERINGS)

        restore_every_migration()

        self.assertEqual(unapplied_migrations(), [])
        self.assertIn(OFFERINGS_TABLE, tables())


@skipIf(MIGRATIONS_ENABLED, "The refusal is about settings that disable migrations")
class RestoringAnEmptyGraphIsRefusedTest(TestCase):

    def test_a_graph_with_no_leaves_is_refused_rather_than_reported_clean(self):
        with self.assertRaisesRegex(AssertionError, "no leaves"):
            restore_every_migration()

    def test_the_graph_really_is_empty_under_these_settings(self):
        self.assertEqual(app_tip("tokens"), [])
