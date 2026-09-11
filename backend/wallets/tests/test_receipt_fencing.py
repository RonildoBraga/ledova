from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.db import connections
from rest_framework.test import APITransactionTestCase

from shared.db import APP_ALIAS, acting_for, configured, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Transaction, Wallet
from wallets.services import transaction_confirmation
from wallets.tasks.confirmation import confirm_pending_transaction
from wallets.tests.test_submission_durability import SubmissionFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"


class ReceiptFencingChecks(SubmissionFixture):
    def setUp(self):
        super().setUp()
        self.sequence = 950

    def pending(self):
        self.sequence += 1
        with acting_for(self.tenant.user.pk):
            result = transaction_confirmation.create_pending_transaction(
                self.wallet, "0x" + f"{self.sequence:064x}", self.recipient, Decimal("2")
            )
            return Transaction.objects.get(pk=result["transaction_id"])

    def finish_while_the_receipt_is_in_flight(self, tx, change, *, succeeded=True):
        provider = Mock(spec=["get_transaction_receipt"])
        retained = []

        def read(tx_hash):
            self.assertEqual(tx_hash, tx.tx_hash)
            change()
            retained.append((self.financial_state(), notification.call_count, balance.call_count))
            return {"transactionHash": tx_hash, "status": int(succeeded), "blockNumber": 17}

        provider.get_transaction_receipt.side_effect = read
        with (
            patch("wallets.tasks.confirmation.get_blockchain_client", return_value=provider),
            patch("wallets.services.transaction_confirmation.send_transaction_notification.defer") as notification,
            patch("wallets.services.transaction_confirmation.sync_holding") as balance,
        ):
            result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)
            self.assertEqual((notification.call_count, balance.call_count), retained[0][1:])
        self.assertEqual(result["status"], "observation_changed")
        self.assertEqual(self.financial_state(), retained[0][0])

    def test_a_late_success_cannot_replace_a_newer_terminal_decision(self):
        for decision in ("failed", "replaced", "reorged"):
            with self.subTest(decision=decision):
                tx = self.pending()

                def decide():
                    if decision == "failed":
                        transaction_confirmation.fail_transaction(tx.tx_hash, wallet=self.wallet)
                    elif decision == "replaced":
                        transaction_confirmation.mark_replaced(tx.tx_hash, self.wallet, "0x" + "59" * 32)
                    else:
                        transaction_confirmation.confirm_transaction(tx.tx_hash, wallet=self.wallet)
                        transaction_confirmation.mark_reorged(tx.tx_hash, self.wallet)

                self.finish_while_the_receipt_is_in_flight(tx, decide)

    def test_changed_transaction_terms_are_not_settled_by_an_older_receipt(self):
        for succeeded in (True, False):
            for changed in ({"nonce": 91}, {"amount": Decimal("3")}, {"imported_from_history": True}):
                with self.subTest(succeeded=succeeded, changed=changed):
                    tx = self.pending()

                    def change():
                        with use_operator():
                            Transaction.objects.filter(pk=tx.pk).update(**changed)

                    self.finish_while_the_receipt_is_in_flight(tx, change, succeeded=succeeded)

    def test_a_recreated_row_at_the_same_hash_does_not_receive_an_older_receipt(self):
        tx = self.pending()

        def recreate():
            with use_operator():
                Transaction.objects.filter(pk=tx.pk).delete()
                replacement = Transaction.objects.create(
                    wallet=self.wallet,
                    tx_hash=tx.tx_hash,
                    chain=self.wallet.chain,
                    from_address=self.wallet.address,
                    to_address=self.recipient,
                    asset=self.native,
                    amount=Decimal("7"),
                    nonce=41,
                )
                self.assertNotEqual(replacement.pk, tx.pk)

        self.finish_while_the_receipt_is_in_flight(tx, recreate)

    def test_a_changed_wallet_address_invalidates_the_captured_context(self):
        tx = self.pending()

        def change():
            with use_operator():
                Wallet.objects.filter(pk=self.wallet.pk).update(address=self.recipient)

        self.finish_while_the_receipt_is_in_flight(tx, change)

    def test_an_unchanged_pending_target_accepts_its_receipt(self):
        tx = self.pending()
        provider = Mock(spec=["get_transaction_receipt"])
        provider.get_transaction_receipt.return_value = {
            "transactionHash": tx.tx_hash,
            "status": 1,
            "blockNumber": 17,
        }
        with (
            patch("wallets.tasks.confirmation.get_blockchain_client", return_value=provider),
            patch("wallets.services.transaction_confirmation.send_transaction_notification.defer") as notification,
        ):
            result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)
            notification.assert_called_once()
        self.assertEqual(result["status"], "confirmed")
        with use_operator():
            tx.refresh_from_db()
        self.assertEqual((tx.status, tx.block_number, tx.amount), ("confirmed", 17, Decimal("2")))

    def test_history_receipts_recheck_the_captured_row_and_accept_a_fresh_observation(self):
        with use_operator():
            tx = Transaction.objects.create(
                wallet=self.wallet,
                tx_hash="0x" + "71" * 32,
                chain=self.wallet.chain,
                from_address=self.wallet.address,
                to_address=self.recipient,
                asset=self.native,
                amount=Decimal("2"),
                imported_from_history=True,
            )

        def change():
            with use_operator():
                Transaction.objects.filter(pk=tx.pk).update(amount=Decimal("3"))

        self.finish_while_the_receipt_is_in_flight(tx, change)
        provider = Mock(spec=["get_transaction_receipt"])
        provider.get_transaction_receipt.return_value = {
            "transactionHash": tx.tx_hash,
            "status": 1,
            "blockNumber": 18,
        }
        holdings_and_snapshots = self.financial_state()[1:]
        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=provider):
            result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(self.financial_state()[1:], holdings_and_snapshots)
        with use_operator():
            tx.refresh_from_db()
        self.assertEqual((tx.amount, tx.block_number), (Decimal("3"), 18))

    @skipUnless(POSTGRES, "Concurrent committed transitions require PostgreSQL")
    def test_another_connection_can_commit_a_failure_while_the_receipt_is_read(self):
        tx = self.pending()

        def fail_in_another_connection():
            try:
                with acting_for(self.tenant.user.pk):
                    return transaction_confirmation.fail_transaction(tx.tx_hash, wallet=self.wallet)
            finally:
                connections.close_all()

        def change():
            with ThreadPoolExecutor(max_workers=1) as worker:
                result = worker.submit(fail_in_another_connection).result(timeout=10)
            self.assertEqual(result["status"], "failed")

        self.finish_while_the_receipt_is_in_flight(tx, change)


class ReceiptFencingTest(ReceiptFencingChecks, APITransactionTestCase):
    pass


class ScopedReceiptFencingTest(RunsOnTheScopedConnection, ReceiptFencingChecks, APITransactionTestCase):
    pass
