from unittest import skipUnless

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APITransactionTestCase

from shared.db import atomic, current_alias, use_operator
from shared.tests.schema import restore_every_migration
from wallets.models import WalletSubmission
from wallets.tests.historical_submissions import (
    historical_financial_state,
    native_submission_at,
)
from wallets.tests.test_global_submission_identity import GlobalSubmissionFixture

BEFORE = ("wallets", "0017_bitcoin_submission")
AFTER = ("wallets", "0018_global_submission_identity")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class GlobalSubmissionMigrationTest(GlobalSubmissionFixture, APITransactionTestCase):
    def old_apps(self):
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        return executor.loader.project_state([BEFORE]).apps

    def test_installation_keeps_existing_signed_intent_and_accounting(self):
        old = self.old_apps()
        signed = self.signed()
        native_submission_at(old, self.wallet, self.native, signed)
        before = historical_financial_state(old)
        journal = list(old.get_model("wallets", "WalletSubmission").objects.values())
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        new = executor.loader.project_state([AFTER]).apps
        self.assertEqual(historical_financial_state(new), before)
        self.assertEqual(list(new.get_model("wallets", "WalletSubmission").objects.values()), journal)
        restore_every_migration()
        current = self.all_financial_state()
        self.assertEqual(self.submit_direct(signed)["status"], "pending")
        self.assertEqual(self.all_financial_state(), current)

    def conflicting_history_is_preserved(self, signed):
        old = self.old_apps()
        native_submission_at(old, self.wallet, self.native, self.signed())
        with use_operator(), atomic():
            native_submission_at(old, self.other_wallet, self.native, signed)
            before = historical_financial_state(old)
            journals = list(old.get_model("wallets", "WalletSubmission").objects.order_by("pk").values())
            self.assertEqual(len(journals), 2)
            with self.assertRaisesRegex(RuntimeError, "retain these rows and reconcile ownership"):
                MigrationExecutor(connection).migrate([AFTER])
            self.assertEqual(historical_financial_state(old), before)
            self.assertEqual(
                list(old.get_model("wallets", "WalletSubmission").objects.order_by("pk").values()), journals
            )
            transaction.set_rollback(True, using=current_alias())
        restore_every_migration()
        with use_operator():
            self.assertEqual(WalletSubmission.objects.count(), 1)

    def test_duplicate_transaction_history_stops_migration_without_rewriting_or_deleting_rows(self):
        self.conflicting_history_is_preserved(self.signed())

    def test_different_transactions_at_one_signer_nonce_stop_migration_without_choosing_an_owner(self):
        self.conflicting_history_is_preserved(self.signed(value=3 * 10**18))
