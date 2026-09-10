from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import ProgrammingError, connections
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from assets.models import Asset, AssetChainDeployment
from assets.services.identity import native_asset_for_chain
from shared.db import APP_ALIAS, acting_for, current_alias, use_operator
from shared.db.aliases import configured
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet
from wallets.services.history_receipts import record_history_receipt
from wallets.services.holdings import sync_holding
from wallets.services.sync import _process_transactions
from wallets.services.transaction_confirmation import TransactionConfirmationService
from wallets.tasks.confirmation import (
    check_all_pending_transactions,
    confirm_pending_transaction,
)


class HistoryPreservationChecks:
    def setUp(self):
        super().setUp()
        with use_operator():
            self.tenant = make_tenant("history-preservation")
            self.wallet = Wallet.objects.create(
                user_account=self.tenant.account,
                address="0x" + "ab" * 20,
                chain="base",
                verification_status="VERIFIED",
            )
            self.native = native_asset_for_chain("base")
            self.native.is_verified = True
            self.native.save(update_fields=["is_verified"])
            self.holding = Holding.objects.create(wallet=self.wallet, asset=self.native, quantity=10)
            self.other_asset = Asset.objects.create(symbol="HISTORY", name="Synthetic history token")
            AssetChainDeployment.objects.create(asset=self.other_asset, chain="base", contract_address="0x" + "cd" * 20)
        for target in (
            "wallets.services.transaction_confirmation.send_transaction_notification.defer",
            "wallets.services.transaction_confirmation.sync_holding",
            "wallets.services.sync.TransactionMonitoringService.check_new_transaction",
        ):
            patched = patch(target, return_value=None)
            self.addCleanup(patched.stop)
            patched.start()

    def history(self, **overrides):
        data = {
            "tx_hash": "0x" + "17" * 32,
            "chain": "base",
            "from_address": self.wallet.address,
            "to_address": "0x" + "ef" * 20,
            "amount": "2",
            "block_timestamp": timezone.now(),
            "block_number": 75,
            "transaction_fee": "0.01",
            "status": "success",
        }
        data.update(overrides)
        return data

    def pending(self):
        with acting_for(self.tenant.user.pk):
            data = self.history()
            TransactionConfirmationService.create_pending_transaction(
                self.wallet, data["tx_hash"], data["to_address"], Decimal("2"), Decimal("0.01")
            )
            return Transaction.objects.get(wallet=self.wallet, tx_hash=data["tx_hash"])

    def state(self):
        with use_operator():
            return (
                list(Transaction.objects.filter(wallet=self.wallet).order_by("pk").values()),
                list(Holding.objects.filter(wallet=self.wallet).order_by("pk").values()),
                list(HoldingSnapshot.objects.filter(holding__wallet=self.wallet).order_by("pk").values()),
            )

    def import_history(self, *entries, wallet=None):
        with acting_for(self.tenant.user.pk):
            return _process_transactions(wallet or self.wallet, list(entries))

    def test_conflicting_history_preserves_every_existing_lifecycle_and_accounting_field(self):
        tx = self.pending()
        with use_operator():
            Transaction.objects.filter(pk=tx.pk).update(
                nonce=4,
                block_hash="0x" + "31" * 32,
                replaced_by_tx_hash="0x" + "32" * 32,
                balance_reconciliation_token=uuid4(),
            )
        for status in ("pending", "confirmed", "failed", "replaced", "reorged", "success"):
            with self.subTest(status=status):
                with use_operator():
                    Transaction.objects.filter(pk=tx.pk).update(status=status)
                before = self.state()
                conflict = self.history(
                    contract_address="0x" + "cd" * 20,
                    amount="900",
                    from_address="0x" + "98" * 20,
                    to_address="0x" + "97" * 20,
                    status="failed" if status == "confirmed" else "confirmed",
                    transaction_fee="300",
                )
                first = self.import_history(conflict)
                second = self.import_history(self.history())
                self.assertEqual(first, {"status": "success", "transactions": 0, "snapshots": 0})
                self.assertEqual(second, first)
                self.assertEqual(self.state(), before)

    def test_existing_hash_does_not_resolve_untrusted_asset_or_parse_replacement_payload(self):
        self.pending()
        before = self.state()
        with patch("wallets.services.sync.quarantine_unknown_token") as quarantine:
            result = self.import_history({"tx_hash": self.history()["tx_hash"]})
        self.assertEqual(result, {"status": "success", "transactions": 0, "snapshots": 0})
        quarantine.assert_not_called()
        self.assertEqual(self.state(), before)

    def test_history_cannot_strand_a_pending_debit_before_the_real_failure_refunds_once(self):
        tx = self.pending()
        with use_operator():
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("7.99"))
        self.import_history(self.history(amount="900", status="success"))
        with acting_for(self.tenant.user.pk):
            first = TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
            second = TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
        self.assertEqual((first["status"], second["status"]), ("failed", "not_pending"))
        with use_operator():
            tx.refresh_from_db()
            self.holding.refresh_from_db()
        self.assertEqual((tx.amount, tx.deducted_amount), (Decimal("2"), Decimal("0")))
        self.assertEqual(self.holding.quantity, Decimal("10"))

    def test_new_history_is_imported_once_without_accepting_provider_status_as_a_receipt(self):
        for index, status in enumerate(("success", "confirmed", "failed", "pending", None, "unexpected")):
            with self.subTest(status=status):
                data = self.history(tx_hash="0x" + f"{index:064x}", status=status)
                first = self.import_history(data)
                self.assertEqual(first, {"status": "success", "transactions": 1, "snapshots": int(index == 0)})
                with use_operator():
                    tx = Transaction.objects.get(wallet=self.wallet, tx_hash=data["tx_hash"])
                    self.assertEqual(tx.status, "pending")
                    self.assertTrue(tx.imported_from_history)
                    self.assertEqual(
                        (tx.amount, tx.asset, tx.user_account), (Decimal("2"), self.native, self.tenant.account)
                    )
                    self.assertEqual(tx.transaction_fee, Decimal("0.01"))
                    self.assertIsNone(tx.deducted_amount)
                    self.assertIsNone(tx.deducted_fee)
                before = self.state()
                self.assertEqual(self.import_history(data), {"status": "success", "transactions": 0, "snapshots": 0})
                self.assertEqual(self.state(), before)

    def test_import_without_status_remains_pending_for_the_confirmation_sweep(self):
        data = self.history()
        data.pop("status")
        self.import_history(data)
        with use_operator():
            Transaction.objects.filter(wallet=self.wallet).update(
                created_at=timezone.now() - timezone.timedelta(minutes=3)
            )
            with patch("wallets.tasks.confirmation.confirm_pending_transaction.defer") as queued:
                check_all_pending_transactions(0)
        self.assertIn(
            {"tx_hash": data["tx_hash"], "wallet_uuid": str(self.wallet.pk), "principal_id": None},
            [entry.kwargs for entry in queued.call_args_list],
        )

    def test_new_import_can_only_complete_through_the_receipt_pipeline(self):
        data = self.history()
        self.import_history(data)
        with patch("wallets.tasks.confirmation.get_blockchain_client") as provider:
            provider.return_value.get_transaction_receipt.return_value = None
            with self.assertRaisesRegex(RuntimeError, "receipt not yet available"):
                confirm_pending_transaction(data["tx_hash"], str(self.wallet.pk), principal_id=self.tenant.user.pk)
            provider.return_value.get_transaction_receipt.return_value = {"status": 0, "blockNumber": 75}
            provider.return_value.get_block_timestamp.return_value = int(timezone.now().timestamp())
            result = confirm_pending_transaction(data["tx_hash"], str(self.wallet.pk), principal_id=self.tenant.user.pk)
        self.assertEqual(result["status"], "failed")
        with use_operator():
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("10"))

    def receipt_client(self, **receipt):
        client = Mock(spec=["get_transaction_receipt", "w3"])
        client.get_transaction_receipt.return_value = {"status": 1, "blockNumber": 75, **receipt}
        client.w3.eth.get_block.return_value = {"timestamp": int(timezone.now().timestamp())}
        return client

    def check_receipt(self, data, client):
        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            return confirm_pending_transaction(data["tx_hash"], str(self.wallet.pk), principal_id=self.tenant.user.pk)

    def test_receipt_outage_keeps_imported_block_metadata(self):
        for index, number in enumerate((75, None)):
            with self.subTest(receipt_block_number=number):
                data = self.history(
                    tx_hash="0x" + f"{index + 100:064x}",
                    block_timestamp=timezone.now() - timezone.timedelta(days=7),
                )
                self.import_history(data)
                client = self.receipt_client(blockNumber=number)
                client.w3.eth.get_block.side_effect = TimeoutError("Synthetic block lookup outage")
                self.assertEqual(self.check_receipt(data, client)["status"], "confirmed")
                with use_operator():
                    tx = Transaction.objects.get(wallet=self.wallet, tx_hash=data["tx_hash"])
                self.assertEqual((tx.block_number, tx.block_timestamp), (75, data["block_timestamp"]))

    def test_history_receipt_updates_available_metadata_without_rewriting_balances_or_snapshots(self):
        data = self.history(block_timestamp=timezone.now() - timezone.timedelta(days=7))
        self.import_history(data)
        before = self.state()[1:]
        timestamp = data["block_timestamp"].replace(microsecond=0) + timezone.timedelta(seconds=12)
        client = self.receipt_client(blockNumber=76, gasUsed=21000, effectiveGasPrice=1000000000)
        client.w3.eth.get_block.return_value = {"timestamp": int(timestamp.timestamp())}
        with (
            patch("wallets.services.transaction_confirmation.sync_holding", wraps=sync_holding),
            patch("wallets.services.holdings.fetch_chain_balance", return_value=Decimal("37")),
        ):
            self.assertEqual(self.check_receipt(data, client)["status"], "confirmed")
        with use_operator():
            tx = Transaction.objects.get(wallet=self.wallet, tx_hash=data["tx_hash"])
        self.assertEqual(
            (tx.block_number, tx.block_timestamp, tx.transaction_fee), (76, timestamp, Decimal("0.000021"))
        )
        self.assertIsNone(tx.balance_reconciliation_token)
        self.assertEqual(self.state()[1:], before)
        before_retry = self.state()
        self.assertEqual(self.check_receipt(data, client)["status"], "already_processed")
        self.assertEqual(self.state(), before_retry)
        with acting_for(self.tenant.user.pk):
            with patch("wallets.services.holdings.fetch_chain_balance", return_value=Decimal("37")):
                sync_holding(self.wallet, self.native)
        with use_operator():
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("37"))

    def test_history_receipts_do_not_notify_but_local_transfers_do(self):
        with patch("wallets.services.transaction_confirmation.send_transaction_notification.defer") as notification:
            for status in (0, 1):
                data = self.history(tx_hash="0x" + f"{status + 200:064x}")
                self.import_history(data)
                result = self.check_receipt(data, self.receipt_client(status=status))
                self.assertEqual(result["status"], "confirmed" if status else "failed")
            notification.assert_not_called()
            local = self.pending()
            self.assertEqual(self.check_receipt(self.history(), self.receipt_client())["status"], "confirmed")
            notification.assert_called_once_with(
                user_id=str(self.tenant.user.pk),
                transaction_id=str(local.pk),
                event_type="confirmed",
            )

    def test_quarantined_history_receipt_never_opens_a_holding_or_snapshot(self):
        data = self.history(contract_address="0x" + "cd" * 20)
        self.import_history(data)
        before = self.state()[1:]
        with (
            patch("wallets.services.transaction_confirmation.sync_holding", wraps=sync_holding),
            patch("wallets.services.holdings.fetch_chain_balance", return_value=Decimal("37")),
        ):
            self.assertEqual(self.check_receipt(data, self.receipt_client())["status"], "confirmed")
        self.assertEqual(self.state()[1:], before)
        with use_operator():
            self.assertFalse(Holding.objects.filter(wallet=self.wallet, asset=self.other_asset).exists())
            tx = Transaction.objects.get(wallet=self.wallet, tx_hash=data["tx_hash"])
            self.assertEqual(tx.asset, self.other_asset)
            self.assertFalse(tx.asset.is_verified)
            self.assertIsNone(tx.balance_reconciliation_token)

    def test_history_without_block_metadata_stays_unknown_after_receipt_verification(self):
        data = self.history(block_timestamp=None, block_number=None)
        self.import_history(data)
        self.assertEqual(self.check_receipt(data, self.receipt_client(blockNumber=None))["status"], "confirmed")
        with use_operator():
            tx = Transaction.objects.get(wallet=self.wallet, tx_hash=data["tx_hash"])
        self.assertIsNone(tx.block_timestamp)
        self.assertIsNone(tx.block_number)

    def test_history_receipt_writer_cannot_change_a_local_transfer_or_a_completed_import(self):
        local = self.pending()
        self.assertFalse(local.imported_from_history)
        before = self.state()
        with acting_for(self.tenant.user.pk):
            refused = record_history_receipt(local.tx_hash, wallet=self.wallet, succeeded=False)
        self.assertEqual(refused["status"], "not_found")
        self.assertEqual(self.state(), before)
        data = self.history(tx_hash="0x" + "61" * 32)
        self.import_history(data)
        self.assertEqual(self.check_receipt(data, self.receipt_client())["status"], "confirmed")
        before = self.state()
        with acting_for(self.tenant.user.pk):
            stale = record_history_receipt(data["tx_hash"], wallet=self.wallet, succeeded=False, block_number=900)
        self.assertEqual(stale, {"status": "already_processed", "current_status": "confirmed"})
        self.assertEqual(self.state(), before)

    def test_same_hash_in_another_wallet_is_a_distinct_history_entry(self):
        tx = self.pending()
        with use_operator():
            other = Wallet.objects.create(user_account=self.tenant.account, address="0x" + "ac" * 20, chain="base")
        before = self.state()
        result = self.import_history(self.history(to_address=other.address), wallet=other)
        self.assertEqual(result["transactions"], 1)
        with acting_for(self.tenant.user.pk):
            self.assertEqual(Transaction.objects.filter(tx_hash=tx.tx_hash).count(), 2)
        self.assertEqual(self.state(), before)

    def test_an_unreadable_new_entry_reports_failure_while_a_valid_entry_is_still_imported(self):
        result = self.import_history({"tx_hash": "unreadable-synthetic"}, self.history())
        self.assertEqual((result["status"], result["transactions"]), ("error", 1))
        with acting_for(self.tenant.user.pk):
            self.assertFalse(Transaction.objects.filter(wallet=self.wallet, tx_hash="unreadable-synthetic").exists())
            self.assertEqual(Transaction.objects.get(wallet=self.wallet).tx_hash, self.history()["tx_hash"])

    def overlapping_history(self, operation, pause_target):
        paused = Event()
        release = Event()
        importer_ready = Event()
        pids = {}

        def hold_before_commit(*args, **kwargs):
            paused.set()
            if not release.wait(10):
                raise AssertionError("The history test did not release its first writer")

        def run(first):
            try:
                with acting_for(self.tenant.user.pk):
                    connection = connections[current_alias()]
                    with connection.cursor() as cursor:
                        cursor.execute("SET lock_timeout = '8s'")
                        cursor.execute("SELECT pg_backend_pid()")
                        pids[first] = cursor.fetchone()[0]
                    if first:
                        return operation()
                    importer_ready.set()
                    return self.import_history(self.history(amount="900"))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            with patch(pause_target, side_effect=hold_before_commit):
                first = pool.submit(run, True)
                try:
                    self.assertTrue(paused.wait(5), "The first writer did not reach its uncommitted side effect")
                    second = pool.submit(run, False)
                    self.assertTrue(importer_ready.wait(5), "The history importer did not connect")
                    self.assertNotEqual(pids[True], pids[False])
                    deadline = monotonic() + 5
                    observed = None
                    while monotonic() < deadline:
                        with connections["default"].cursor() as cursor:
                            cursor.execute(
                                "SELECT query, %s = ANY(pg_blocking_pids(pid)), wait_event_type "
                                "FROM pg_stat_activity WHERE pid = %s",
                                [pids[True], pids[False]],
                            )
                            observed = cursor.fetchone()
                        if observed and observed[1] and observed[2] == "Lock" and observed[0] != "BEGIN":
                            break
                        if second.done():
                            self.fail(f"History import finished before the first writer committed: {second.result()}")
                        sleep(0.01)
                    self.assertIsNotNone(observed)
                    self.assertTrue(observed[1], "The history importer did not wait on the first writer")
                    self.assertEqual(observed[2], "Lock")
                    self.assertIn('FROM "wallets"', observed[0])
                    self.assertIn("FOR UPDATE", observed[0])
                finally:
                    release.set()
                return first.result(timeout=10), second.result(timeout=10)

    @skipUnless(connections[configured(APP_ALIAS)].vendor == "postgresql", "Concurrent row locks need PostgreSQL")
    def test_history_waits_for_pending_creation_and_preserves_its_original_deduction(self):
        first, second = self.overlapping_history(
            self.pending, "wallets.services.sync.TransactionMonitoringService.check_new_transaction"
        )
        self.assertEqual(second, {"status": "success", "transactions": 0, "snapshots": 0})
        with use_operator():
            first.refresh_from_db()
            self.holding.refresh_from_db()
            self.assertEqual(Transaction.objects.filter(wallet=self.wallet).count(), 1)
        self.assertEqual(
            (first.status, first.amount, first.deducted_amount), ("pending", Decimal("2"), Decimal("2.01"))
        )
        self.assertEqual(self.holding.quantity, Decimal("7.99"))

    @skipUnless(connections[configured(APP_ALIAS)].vendor == "postgresql", "Concurrent row locks need PostgreSQL")
    def test_history_waits_for_confirmation_and_preserves_the_committed_receipt(self):
        tx = self.pending()
        timestamp = timezone.now()

        def confirm():
            return TransactionConfirmationService.confirm_transaction(
                tx.tx_hash, wallet=self.wallet, block_number=80, block_timestamp=timestamp, actual_fee=Decimal("0.003")
            )

        first, second = self.overlapping_history(
            confirm, "wallets.services.transaction_confirmation.send_transaction_notification.defer"
        )
        self.assertEqual(first["status"], "confirmed")
        self.assertEqual(second["transactions"], 0)
        with use_operator():
            tx.refresh_from_db()
        self.assertEqual((tx.status, tx.block_number, tx.block_timestamp), ("confirmed", 80, timestamp))
        self.assertEqual(
            (tx.amount, tx.transaction_fee, tx.deducted_amount), (Decimal("2"), Decimal("0.003"), Decimal("2.01"))
        )

    @skipUnless(connections[configured(APP_ALIAS)].vendor == "postgresql", "Concurrent row locks need PostgreSQL")
    def test_overlapping_history_imports_keep_the_first_observation_and_one_snapshot(self):
        first, second = self.overlapping_history(
            lambda: self.import_history(self.history()),
            "wallets.services.sync.TransactionMonitoringService.check_new_transaction",
        )
        self.assertEqual(first, {"status": "success", "transactions": 1, "snapshots": 1})
        self.assertEqual(second, {"status": "success", "transactions": 0, "snapshots": 0})
        with use_operator():
            self.assertEqual(Transaction.objects.get(wallet=self.wallet).amount, Decimal("2"))
            self.assertEqual(HoldingSnapshot.objects.filter(holding=self.holding).count(), 1)


class HistoryPreservationTest(HistoryPreservationChecks, APITransactionTestCase):
    pass


class ScopedHistoryPreservationTest(RunsOnTheScopedConnection, HistoryPreservationChecks, APITransactionTestCase):
    def test_a_foreign_principal_cannot_verify_an_imported_receipt(self):
        data = self.history()
        self.import_history(data)
        with use_operator():
            other = make_tenant("foreign-receipt")
        before = self.state()
        with acting_for(other.user.pk):
            with self.assertRaises(Wallet.DoesNotExist):
                record_history_receipt(data["tx_hash"], wallet=self.wallet, succeeded=True)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.check_receipt(data, self.receipt_client())["status"], "confirmed")

    def test_a_visible_foreign_operator_wallet_cannot_receive_history(self):
        with use_operator():
            other = make_tenant("foreign-history")
            before = list(Transaction.objects.filter(wallet=other.wallet).values())
        with acting_for(self.tenant.user.pk):
            self.assertTrue(Wallet.objects.filter(pk=other.wallet.pk).exists())
        with self.assertRaisesRegex(ProgrammingError, "row-level security policy"):
            self.import_history(self.history(), wallet=other.wallet)
        with use_operator():
            self.assertEqual(list(Transaction.objects.filter(wallet=other.wallet).values()), before)
        self.assertEqual(self.import_history(self.history())["transactions"], 1)
