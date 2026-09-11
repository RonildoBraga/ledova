from unittest import skipUnless

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APITransactionTestCase

from shared.db import acting_for, atomic, current_alias, use_operator
from shared.tests.schema import restore_every_migration
from tokens.services.signed_transactions import decode_signed_transaction
from wallets.models import WalletSubmission
from wallets.services.submissions import _record_submission
from wallets.tests.test_global_submission_identity import GlobalSubmissionFixture

BEFORE = ("wallets", "0017_bitcoin_submission")
AFTER = ("wallets", "0018_global_submission_identity")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class GlobalSubmissionMigrationTest(GlobalSubmissionFixture, APITransactionTestCase):
    def test_installation_keeps_existing_signed_intent_and_accounting(self):
        self.addCleanup(restore_every_migration)
        signed = self.signed()
        self.submit_direct(signed)
        MigrationExecutor(connection).migrate([BEFORE])
        before = self.all_financial_state()
        with use_operator():
            journal = list(WalletSubmission.objects.values())
        MigrationExecutor(connection).migrate([AFTER])
        self.assertEqual(self.all_financial_state(), before)
        with use_operator():
            self.assertEqual(list(WalletSubmission.objects.values()), journal)
        self.assertEqual(self.submit_direct(signed)["status"], "pending")
        self.assertEqual(self.all_financial_state(), before)

    def _conflicting_history_is_preserved(self, signed):
        self.addCleanup(restore_every_migration)
        self.submit_direct(self.signed())
        MigrationExecutor(connection).migrate([BEFORE])
        raw = bytes(signed.raw_transaction)
        decoded = decode_signed_transaction(raw)
        with acting_for(self.other.user.pk), atomic():
            _record_submission(self.other_wallet, raw, decoded, signed.hash.to_0x_hex(), None)
            before = self.all_financial_state()
            with use_operator():
                journals = list(WalletSubmission.objects.order_by("pk").values())
            self.assertEqual(len(journals), 2)
            with self.assertRaisesRegex(RuntimeError, "retain these rows and reconcile ownership"):
                MigrationExecutor(connection).migrate([AFTER])
            self.assertEqual(self.all_financial_state(), before)
            with use_operator():
                self.assertEqual(list(WalletSubmission.objects.order_by("pk").values()), journals)
            transaction.set_rollback(True, using=current_alias())
        restore_every_migration()
        with use_operator():
            self.assertEqual(WalletSubmission.objects.count(), 1)

    def test_duplicate_transaction_history_stops_migration_without_rewriting_or_deleting_rows(self):
        self._conflicting_history_is_preserved(self.signed())

    def test_different_transactions_at_one_signer_nonce_stop_migration_without_choosing_an_owner(self):
        self._conflicting_history_is_preserved(self.signed(value=3 * 10**18))
