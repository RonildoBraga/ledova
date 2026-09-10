from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from unittest import skipUnless
from unittest.mock import Mock, call, patch

from django.db import connections
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from assets.models import Asset, AssetChainDeployment
from assets.services.identity import native_asset_for_chain
from shared.db import APP_ALIAS, acting_for, current_alias, use_operator
from shared.db.aliases import configured
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.models import Holding, HoldingSnapshot, Transaction, Wallet
from wallets.services.holdings import sync_holding
from wallets.services.transaction_confirmation import TransactionConfirmationService
from wallets.tasks.confirmation import (
    check_all_pending_transactions,
    cleanup_stale_pending_transactions,
    confirm_pending_transaction,
)


class ConfirmationChecks:
    def setUp(self):
        super().setUp()
        with use_operator():
            self.tenant = make_tenant("confirmation-lock")
            self.wallet = Wallet.objects.create(
                user_account=self.tenant.account, address="0x" + "51" * 20, chain="base", verification_status="VERIFIED"
            )
            self.asset = Asset.objects.create(
                symbol="REFUND", name="Synthetic refund token", asset_type="erc20_token", is_verified=True
            )
            self.contract = "0x" + "52" * 20
            AssetChainDeployment.objects.create(asset=self.asset, chain="base", contract_address=self.contract)
            self.native = native_asset_for_chain("base")
            Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=100)
            Holding.objects.create(wallet=self.wallet, asset=self.native, quantity=5)
        notification = patch("wallets.services.transaction_confirmation.send_transaction_notification.defer")
        self.addCleanup(notification.stop)
        self.notification = notification.start()
        self.balance_observations = []
        self.chain_available = False
        self.token_balance = Decimal("100")
        self.native_balance = Decimal("5")
        balance = patch("wallets.services.holdings.fetch_chain_balance", side_effect=self.read_balance)
        self.addCleanup(balance.stop)
        balance.start()

    def read_balance(self, wallet, asset):
        alias = current_alias()
        self.balance_observations.append((alias, connections[alias].in_atomic_block))
        if not self.chain_available:
            return None
        return self.token_balance if asset == self.asset else self.native_balance

    def pending(self, tx_hash="0x" + "53" * 32):
        with acting_for(self.tenant.user.pk):
            TransactionConfirmationService.create_pending_transaction(
                self.wallet,
                tx_hash,
                "0x" + "54" * 20,
                Decimal("1.5"),
                transaction_fee=Decimal("0.002"),
                token_contract=self.contract,
            )
            return Transaction.objects.get(tx_hash=tx_hash, wallet=self.wallet)

    def quantities(self):
        with use_operator():
            return (
                Holding.objects.get(wallet=self.wallet, asset=self.asset).quantity,
                Holding.objects.get(wallet=self.wallet, asset=self.native).quantity,
            )

    def send_in_another_connection(self):
        def send():
            try:
                return self.pending()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as worker:
            return worker.submit(send).result(timeout=8)

    def test_two_reversals_using_stale_instances_restore_only_the_outstanding_debit(self):
        tx = self.pending()
        with acting_for(self.tenant.user.pk):
            stale = Transaction.objects.get(pk=tx.pk)
            TransactionConfirmationService._revert_optimistic_holding(tx)
            TransactionConfirmationService._revert_optimistic_holding(stale)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        with use_operator():
            tx.refresh_from_db()
            self.assertEqual((tx.deducted_amount, tx.deducted_fee), (Decimal("0"), Decimal("0")))

    def test_failure_refreshes_chain_truth_after_a_sync_superseded_the_deduction(self):
        tx = self.pending()
        self.chain_available = True
        with acting_for(self.tenant.user.pk):
            sync_holding(self.wallet, self.asset)
            sync_holding(self.wallet, self.native)
            self.balance_observations.clear()
            result = TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        self.assertEqual(self.balance_observations, [(configured(APP_ALIAS), False)] * 2)

    def test_confirmation_reads_balances_after_releasing_the_transaction(self):
        tx = self.pending()
        self.chain_available = True
        self.token_balance = Decimal("98.5")
        self.native_balance = Decimal("4.999")
        with acting_for(self.tenant.user.pk):
            result = TransactionConfirmationService.confirm_transaction(
                tx.tx_hash, actual_fee=Decimal("0.001"), wallet=self.wallet
            )
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(self.quantities(), (self.token_balance, self.native_balance))
        self.assertEqual(self.balance_observations, [(configured(APP_ALIAS), False)] * 2)

    def duplicate_jobs(self, method, tx):
        first_is_waiting = Event()
        second_is_writing = Event()
        release_first = Event()

        def hold_first_commit(**kwargs):
            if not first_is_waiting.is_set():
                first_is_waiting.set()
                if not release_first.wait(10):
                    raise AssertionError("The duplicate job did not reach its database write")

        self.notification.side_effect = hold_first_commit

        def run(second=False):
            try:
                with acting_for(self.tenant.user.pk):
                    connection = connections[current_alias()]
                    with connection.cursor() as cursor:
                        cursor.execute("SET lock_timeout = '8s'")

                    def observe(execute, sql, params, many, context):
                        if second and ("FOR UPDATE" in sql or sql.lstrip().startswith('UPDATE "transactions"')):
                            second_is_writing.set()
                        return execute(sql, params, many, context)

                    with connection.execute_wrapper(observe):
                        return method(tx.tx_hash, wallet=self.wallet)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(run)
            try:
                self.assertTrue(first_is_waiting.wait(8), "The first job never reached its commit boundary")
                second = workers.submit(run, True)
                self.assertTrue(second_is_writing.wait(5), "The duplicate job never reached the contested write")
            finally:
                release_first.set()
            return [first.result(timeout=10), second.result(timeout=10)]

    @skipUnless(connections[configured(APP_ALIAS)].vendor == "postgresql", "Concurrent row locks need PostgreSQL")
    def test_duplicate_failure_jobs_return_the_debit_and_notify_once(self):
        tx = self.pending()
        results = self.duplicate_jobs(TransactionConfirmationService.fail_transaction, tx)
        self.assertEqual(sorted(result["status"] for result in results), ["failed", "not_pending"])
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        self.notification.assert_called_once()

    @skipUnless(connections[configured(APP_ALIAS)].vendor == "postgresql", "Concurrent row locks need PostgreSQL")
    def test_duplicate_confirmation_jobs_commit_and_notify_once(self):
        tx = self.pending()
        results = self.duplicate_jobs(TransactionConfirmationService.confirm_transaction, tx)
        self.assertEqual(sorted(result["status"] for result in results), ["already_confirmed", "confirmed"])
        self.notification.assert_called_once()

    def test_the_same_hash_on_another_wallet_keeps_its_own_status_and_holding(self):
        tx = self.pending()
        with use_operator():
            other = Wallet.objects.create(
                user_account=self.tenant.account, address="0x" + "55" * 20, chain="base", verification_status="VERIFIED"
            )
            theirs = Transaction.objects.create(
                wallet=other,
                tx_hash=tx.tx_hash,
                chain="base",
                from_address=self.wallet.address,
                to_address=other.address,
                asset=self.asset,
                amount=tx.amount,
            )
        with acting_for(self.tenant.user.pk):
            result = TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet)
        self.assertEqual(result["status"], "confirmed")
        with use_operator():
            theirs.refresh_from_db()
            self.assertEqual(theirs.status, "pending")
            self.assertFalse(Holding.objects.filter(wallet=other).exists())
        self.notification.assert_called_once()

    def test_failure_still_restores_an_outstanding_debit_when_the_provider_is_unavailable(self):
        tx = self.pending()
        with acting_for(self.tenant.user.pk):
            result = TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        self.assertEqual(self.balance_observations, [(configured(APP_ALIAS), False)] * 2)

    def test_a_sync_then_a_provider_outage_cannot_turn_a_reversal_into_income(self):
        tx = self.pending()
        self.chain_available = True
        with acting_for(self.tenant.user.pk):
            sync_holding(self.wallet, self.asset)
            sync_holding(self.wallet, self.native)
            self.chain_available = False
            result = TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_a_token_sync_does_not_discard_the_still_outstanding_native_fee(self):
        tx = self.pending()
        self.chain_available = True
        with acting_for(self.tenant.user.pk):
            sync_holding(self.wallet, self.asset)
            self.chain_available = False
            TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_two_pending_debits_in_the_same_generation_can_each_be_returned_once(self):
        first = self.pending()
        second = self.pending("0x" + "56" * 32)
        self.assertEqual(self.quantities(), (Decimal("97"), Decimal("4.996")))
        with acting_for(self.tenant.user.pk):
            TransactionConfirmationService.fail_transaction(first.tx_hash, wallet=self.wallet)
            TransactionConfirmationService.fail_transaction(second.tx_hash, wallet=self.wallet)
            TransactionConfirmationService.fail_transaction(first.tx_hash, wallet=self.wallet)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def test_a_balance_read_cannot_overwrite_a_debit_made_while_the_provider_was_answering(self):
        def send_during_read(wallet, asset):
            self.send_in_another_connection()
            return Decimal("100")

        with acting_for(self.tenant.user.pk):
            with patch("wallets.services.holdings.fetch_chain_balance", side_effect=send_during_read):
                result = sync_holding(self.wallet, self.asset)
        self.assertIsNone(result)
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))

    def test_a_balance_read_cannot_overwrite_a_holding_created_while_the_provider_was_answering(self):
        with use_operator():
            Holding.objects.filter(wallet=self.wallet, asset=self.asset).delete()

        def send_during_read(wallet, asset):
            self.send_in_another_connection()
            return Decimal("100")

        with acting_for(self.tenant.user.pk):
            with patch("wallets.services.holdings.fetch_chain_balance", side_effect=send_during_read):
                result = sync_holding(self.wallet, self.asset)
        self.assertIsNone(result)
        self.assertEqual(self.quantities(), (Decimal("0"), Decimal("4.998")))

    def test_a_legacy_row_waits_for_chain_truth_instead_of_guessing_a_refund(self):
        tx = self.pending()
        with acting_for(self.tenant.user.pk):
            Transaction.objects.filter(pk=tx.pk).update(
                deducted_amount_sync_version=None, deducted_fee_sync_version=None
            )
            result = TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
            tx.refresh_from_db()
            self.assertEqual((tx.deducted_amount, tx.deducted_fee), (Decimal("0"), Decimal("0")))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))
        self.chain_available = True
        with acting_for(self.tenant.user.pk):
            sync_holding(self.wallet, self.asset)
            sync_holding(self.wallet, self.native)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))

    def assert_a_confirmation_repair_survives_failure(self, boundary):
        tx = self.pending()
        self.chain_available = True
        self.token_balance = Decimal("98.5")
        self.native_balance = Decimal("4.999")
        with acting_for(self.tenant.user.pk):
            with patch.object(
                TransactionConfirmationService, boundary, side_effect=RuntimeError("Synthetic interruption")
            ):
                with self.assertRaises(RuntimeError):
                    TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet, block_number=77)
            tx.refresh_from_db()
            self.assertEqual(tx.status, "confirmed")
            self.assertIsNotNone(tx.balance_reconciliation_token)
        with patch("wallets.tasks.confirmation.get_blockchain_client") as receipt_client:
            result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)
        self.assertEqual(result["status"], "reconciled")
        receipt_client.assert_not_called()
        self.notification.assert_called_once()
        with use_operator():
            tx.refresh_from_db()
            self.assertIsNone(tx.balance_reconciliation_token)
            self.assertEqual(
                HoldingSnapshot.objects.get(holding__wallet=self.wallet, holding__asset=self.asset).block_number, 77
            )
        self.assertEqual(self.quantities(), (self.token_balance, self.native_balance))

    def test_a_worker_interrupted_after_confirmation_commits_can_repair_on_retry(self):
        self.assert_a_confirmation_repair_survives_failure("_verify_holding_balance")

    def test_a_failed_snapshot_write_keeps_the_committed_confirmation_repairable(self):
        self.assert_a_confirmation_repair_survives_failure("_update_snapshot_on_confirmation")

    def test_the_sweep_requeues_a_confirmed_transaction_with_unfinished_balance_work(self):
        tx = self.pending()
        with acting_for(self.tenant.user.pk):
            TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet)
            Transaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(minutes=3))
        with use_operator(), patch("wallets.tasks.confirmation.confirm_pending_transaction.defer") as queued:
            check_all_pending_transactions(0)
        queued.assert_called_once_with(tx_hash=tx.tx_hash, wallet_uuid=str(self.wallet.pk), principal_id=None)

    def test_overdue_cleanup_preserves_the_outstanding_debit_without_provider_or_refund(self):
        tx = self.pending()
        with use_operator():
            Transaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(hours=48))
            before = Transaction.objects.filter(pk=tx.pk).values().get()
            holdings = list(Holding.objects.filter(wallet=self.wallet).order_by("pk").values())
            snapshots = list(HoldingSnapshot.objects.filter(holding__wallet=self.wallet).order_by("pk").values())

        with use_operator(), patch("wallets.tasks.confirmation.get_blockchain_client") as receipt_client:
            first = cleanup_stale_pending_transactions(timestamp=0)
            second = cleanup_stale_pending_transactions(timestamp=0)
            self.assertEqual(Transaction.objects.filter(pk=tx.pk).values().get(), before)
            self.assertEqual(list(Holding.objects.filter(wallet=self.wallet).order_by("pk").values()), holdings)
            self.assertEqual(
                list(HoldingSnapshot.objects.filter(holding__wallet=self.wallet).order_by("pk").values()), snapshots
            )

        self.assertEqual(first, {"total": 1, "failed": 0})
        self.assertEqual(second, first)
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))
        self.assertEqual(self.balance_observations, [])
        self.notification.assert_not_called()
        receipt_client.assert_not_called()

    def test_an_overdue_transaction_is_requeued_and_confirmed_after_a_missing_receipt(self):
        tx = self.pending()
        with use_operator():
            Transaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(hours=48))
            cleanup_stale_pending_transactions(timestamp=0)
        client = Mock(spec=["get_transaction_receipt"])
        client.get_transaction_receipt.side_effect = [
            None,
            {"status": 1, "blockNumber": 77, "gasUsed": 21000, "effectiveGasPrice": 10**9},
        ]

        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "receipt not yet available"):
                confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=None)
            with use_operator(), patch("wallets.tasks.confirmation.confirm_pending_transaction.defer") as queued:
                tx.refresh_from_db()
                self.assertEqual(tx.status, "pending")
                self.assertEqual((tx.deducted_amount, tx.deducted_fee), (Decimal("1.5"), Decimal("0.002")))
                cleanup_stale_pending_transactions(timestamp=0)
                self.assertEqual(check_all_pending_transactions(timestamp=0), {"total": 1, "queued": 1})
            queued.assert_called_once_with(tx_hash=tx.tx_hash, wallet_uuid=str(self.wallet.pk), principal_id=None)
            self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.998")))
            self.notification.assert_not_called()

            self.chain_available = True
            self.token_balance = Decimal("98.5")
            self.native_balance = Decimal("4.999979")
            result = confirm_pending_transaction(**queued.call_args.kwargs)

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(client.get_transaction_receipt.call_args_list, [call(tx.tx_hash), call(tx.tx_hash)])
        self.assertEqual(self.quantities(), (self.token_balance, self.native_balance))
        self.notification.assert_called_once()
        with use_operator():
            tx.refresh_from_db()
            self.assertEqual(tx.status, "confirmed")
            self.assertEqual((tx.block_number, tx.transaction_fee), (77, Decimal("0.000021")))
            self.assertIsNone(tx.balance_reconciliation_token)

    def test_overdue_cleanup_keeps_terminal_outcomes_and_unfinished_balance_repair(self):
        for index, status in enumerate(("confirmed", "failed", "replaced", "reorged"), start=200):
            tx = self.pending("0x" + f"{index:064x}")
            with acting_for(self.tenant.user.pk):
                if status in ("confirmed", "reorged"):
                    TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet)
                if status == "failed":
                    TransactionConfirmationService.fail_transaction(tx.tx_hash, wallet=self.wallet)
                elif status == "replaced":
                    TransactionConfirmationService.mark_replaced(tx.tx_hash, self.wallet, "0x" + "57" * 32)
                elif status == "reorged":
                    TransactionConfirmationService.mark_reorged(tx.tx_hash, self.wallet)
                Transaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(hours=48))

        with use_operator():
            before = list(Transaction.objects.filter(wallet=self.wallet).order_by("pk").values())
            holdings = list(Holding.objects.filter(wallet=self.wallet).order_by("pk").values())
            snapshots = list(HoldingSnapshot.objects.filter(holding__wallet=self.wallet).order_by("pk").values())
            unfinished = set(
                Transaction.objects.filter(wallet=self.wallet, balance_reconciliation_token__isnull=False).values_list(
                    "tx_hash", flat=True
                )
            )
            self.assertEqual({row["status"] for row in before}, {"confirmed", "failed", "replaced", "reorged"})
            self.assertEqual(len(unfinished), 3)
        self.notification.reset_mock()
        self.balance_observations.clear()

        with use_operator(), patch("wallets.tasks.confirmation.confirm_pending_transaction.defer") as queued:
            report = cleanup_stale_pending_transactions(timestamp=0)
            self.assertEqual(list(Transaction.objects.filter(wallet=self.wallet).order_by("pk").values()), before)
            self.assertEqual(list(Holding.objects.filter(wallet=self.wallet).order_by("pk").values()), holdings)
            self.assertEqual(
                list(HoldingSnapshot.objects.filter(holding__wallet=self.wallet).order_by("pk").values()), snapshots
            )
            self.assertEqual(check_all_pending_transactions(timestamp=0), {"total": 3, "queued": 3})
        self.assertEqual(report, {"total": 0, "failed": 0})
        self.assertEqual({job.kwargs["tx_hash"] for job in queued.call_args_list}, unfinished)
        self.assertEqual(self.balance_observations, [])
        self.notification.assert_not_called()

    def test_an_explicit_late_revert_returns_the_outstanding_debit_once(self):
        tx = self.pending()
        with use_operator():
            Transaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(hours=48))
        client = Mock(spec=["get_transaction_receipt"])
        client.get_transaction_receipt.return_value = {"status": 0, "blockNumber": 77}

        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=None)
            repeated = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=None)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "Transaction reverted on-chain")
        self.assertEqual(repeated["status"], "reconciliation_pending")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        self.notification.assert_called_once()
        client.get_transaction_receipt.assert_called_once_with(tx.tx_hash)
        with use_operator():
            tx.refresh_from_db()
            self.assertEqual(tx.status, "failed")
            self.assertEqual((tx.deducted_amount, tx.deducted_fee), (Decimal("0"), Decimal("0")))
            self.assertIsNotNone(tx.balance_reconciliation_token)

    def test_a_reorg_after_the_confirmation_sync_restores_chain_truth_once(self):
        tx = self.pending()
        self.chain_available = True
        self.token_balance = Decimal("98.5")
        self.native_balance = Decimal("4.999")
        with acting_for(self.tenant.user.pk):
            TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet)
            self.token_balance = Decimal("100")
            self.native_balance = Decimal("5")
            result = TransactionConfirmationService.mark_reorged(tx.tx_hash, self.wallet)
            TransactionConfirmationService.mark_reorged(tx.tx_hash, self.wallet)
            tx.refresh_from_db()
            self.assertIsNone(tx.balance_reconciliation_token)
            self.assertEqual((tx.deducted_amount, tx.deducted_fee), (Decimal("0"), Decimal("0")))
        self.assertEqual(result["status"], "reorged")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        self.assertEqual(self.notification.call_count, 2)

    def test_a_reorg_during_an_outage_retains_its_deductions_until_a_retry_can_refresh(self):
        tx = self.pending()
        self.chain_available = True
        self.token_balance = Decimal("98.5")
        self.native_balance = Decimal("4.999")
        with acting_for(self.tenant.user.pk):
            TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet)
            self.chain_available = False
            TransactionConfirmationService.mark_reorged(tx.tx_hash, self.wallet)
            tx.refresh_from_db()
            self.assertIsNotNone(tx.balance_reconciliation_token)
            self.assertEqual(tx.deducted_amount, Decimal("1.5"))
        self.assertEqual(self.quantities(), (Decimal("98.5"), Decimal("4.999")))
        self.chain_available = True
        self.token_balance = Decimal("100")
        self.native_balance = Decimal("5")
        result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))
        self.assertEqual(self.notification.call_count, 2)
        with use_operator():
            tx.refresh_from_db()
            self.assertIsNone(tx.balance_reconciliation_token)
            self.assertEqual((tx.deducted_amount, tx.deducted_fee), (Decimal("0"), Decimal("0")))

    def test_an_older_confirmation_repair_cannot_finish_over_a_newer_reorg(self):
        tx = self.pending()
        self.chain_available = True
        self.token_balance = Decimal("98.5")
        self.native_balance = Decimal("4.999")
        verify = TransactionConfirmationService._verify_holding_balance
        first = True

        def reorg_during_repair(wallet, asset):
            nonlocal first
            result = verify(wallet, asset)
            if first:
                first = False
                self.token_balance = Decimal("100")
                self.native_balance = Decimal("5")
                TransactionConfirmationService.mark_reorged(tx.tx_hash, self.wallet)
            return result

        with acting_for(self.tenant.user.pk):
            with patch.object(
                TransactionConfirmationService, "_verify_holding_balance", side_effect=reorg_during_repair
            ):
                with patch.object(TransactionConfirmationService, "_update_snapshot_on_confirmation") as snapshot:
                    TransactionConfirmationService.confirm_transaction(tx.tx_hash, wallet=self.wallet, block_number=77)
            snapshot.assert_not_called()
            tx.refresh_from_db()
            self.assertEqual(tx.status, "reorged")
            self.assertIsNone(tx.balance_reconciliation_token)
        self.assertEqual(self.quantities(), (Decimal("100"), Decimal("5")))


class ConfirmationLockingTest(ConfirmationChecks, APITransactionTestCase):
    pass


class ScopedConfirmationLockingTest(RunsOnTheScopedConnection, ConfirmationChecks, APITransactionTestCase):
    pass
