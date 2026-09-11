from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from shared.tests.schema import restore_every_migration
from wallets.models import BitcoinSubmission, BitcoinSubmissionInput, Transaction
from wallets.tests.test_bitcoin_submission import FIXTURE, BitcoinSubmissionFixture

BEFORE = ("wallets", "0016_wallet_submission")
AFTER = ("wallets", "0017_bitcoin_submission")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
@override_settings(BITCOIN_NETWORK="regtest")
class BitcoinSubmissionMigrationTest(BitcoinSubmissionFixture, APITransactionTestCase):
    def test_existing_history_is_preserved_without_creating_signed_intent_or_reservations(self):
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        old = executor.loader.project_state([BEFORE]).apps
        transactions = old.get_model("wallets", "Transaction").objects
        existing_count = transactions.count()
        for index, status in enumerate(("pending", "confirmed", "failed", "replaced", "reorged", "success")):
            transactions.create(
                wallet_id=self.wallet.pk,
                user_account_id=self.tenant.account.pk,
                asset_id=self.asset.pk,
                tx_hash=f"{index + 820:064x}",
                chain="bitcoin",
                from_address=self.wallet.address,
                to_address=FIXTURE["recipient"],
                amount=Decimal("1.25"),
                transaction_fee_estimated=Decimal("0.0004"),
                transaction_fee=Decimal("0.0003") if index else None,
                deducted_amount=Decimal("1.2504") if index == 0 else None,
                status=status,
                imported_from_history=index % 2 == 1,
            )
        before = list(transactions.order_by("pk").values())
        self.assertEqual(len(before), existing_count + 6)
        MigrationExecutor(connection).migrate([AFTER])
        with use_operator():
            self.assertEqual(list(Transaction.objects.order_by("pk").values()), before)
            self.assertEqual(BitcoinSubmission.objects.count(), 0)
            self.assertEqual(BitcoinSubmissionInput.objects.count(), 0)
        restore_every_migration()
        self.assertEqual(self.submit_direct()["status"], "pending")
        self.assertEqual(self.submission().tx_hash, FIXTURE["txid"])

    def test_rollback_cannot_discard_committed_signed_bytes_and_inputs(self):
        self.addCleanup(restore_every_migration)
        self.submit_direct()
        before = self.transactions()
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded intent"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(self.transactions(), before)
        self.assertEqual(bytes(self.submission().raw_transaction), bytes.fromhex(FIXTURE["raw_transaction"]))
        with use_operator():
            self.assertEqual(BitcoinSubmissionInput.objects.count(), 1)

    def test_a_missing_input_reservation_prevents_commit_and_broadcast(self):
        with patch.object(BitcoinSubmissionInput.objects.__class__, "bulk_create", return_value=[]):
            with self.assertRaises(DatabaseError):
                self.submit_direct()
        self.assertEqual(self.transactions(), [])
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.quantity(), Decimal("50"))
        with use_operator():
            self.assertEqual(BitcoinSubmission.objects.count(), 0)
