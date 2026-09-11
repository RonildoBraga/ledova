from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from shared.tests.schema import restore_every_migration
from wallets.models import Transaction, WalletSubmission
from wallets.tests.test_submission_durability import SubmissionFixture

BEFORE = ("wallets", "0015_transaction_imported_from_history")
AFTER = ("wallets", "0016_wallet_submission")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class SubmissionMigrationTest(SubmissionFixture, APITransactionTestCase):
    def test_installing_the_journal_preserves_existing_rows_without_adopting_them(self):
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
                asset_id=self.native.pk,
                tx_hash="0x" + f"{index + 800:064x}",
                chain=self.wallet.chain,
                from_address=self.wallet.address,
                to_address=self.recipient,
                amount=Decimal("1.25"),
                transaction_fee_estimated=Decimal("0.0004"),
                transaction_fee=Decimal("0.0003") if index else None,
                deducted_amount=Decimal("1.2504") if index == 0 else None,
                nonce=index,
                status=status,
                imported_from_history=index % 2 == 1,
                block_number=125 if index else None,
                block_timestamp=timezone.now() - timezone.timedelta(days=3) if index else None,
            )
        before = list(transactions.order_by("pk").values())
        self.assertEqual(len(before), existing_count + 6)
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        with use_operator():
            self.assertEqual(list(Transaction.objects.order_by("pk").values()), before)
            self.assertEqual(WalletSubmission.objects.count(), 0)
        signed = self.signed()
        with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)):
            self.assertEqual(self.submit_direct(signed)["status"], "pending")
        self.assertEqual(self.submission().tx_hash, signed.hash.to_0x_hex())

    def test_rollback_refuses_to_discard_a_committed_signed_submission(self):
        self.addCleanup(restore_every_migration)
        signed = self.signed()
        with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)):
            self.submit_direct(signed)
        before = self.financial_state()
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded intent"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(bytes(self.submission().raw_transaction), bytes(signed.raw_transaction))
