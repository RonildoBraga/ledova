from datetime import timedelta
from unittest.mock import Mock, call, patch

from django.test import TestCase
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus
from blockchain.services import TransactionMonitorService
from blockchain.tasks import check_pending_transactions, cleanup_failed_transactions

TX_HASH = "0x" + "71" * 32
BLOCK_HASH = "0x" + "72" * 32
CONFIRMED_RECEIPT = {"status": 1, "blockNumber": 77, "blockHash": BLOCK_HASH, "gasUsed": 21000}


class OverdueTransactionMonitorTest(TestCase):
    def transaction(self, tx_hash=TX_HASH, status=TransactionStatus.SUBMITTED, *, hours=48):
        tx = BlockchainTransaction.objects.create(
            tx_hash=tx_hash,
            status=status,
            from_address="0x" + "73" * 20,
            to_address="0x" + "74" * 20,
            nonce=7,
            submitted_at=timezone.now(),
            error_message="Waiting for a receipt",
        )
        BlockchainTransaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(hours=hours))
        tx.refresh_from_db()
        return tx

    def stored_transactions(self):
        return list(BlockchainTransaction.objects.order_by("pk").values())

    def test_cleanup_retains_pending_and_submitted_rows_with_or_without_hashes(self):
        for index, status in enumerate((TransactionStatus.PENDING, TransactionStatus.SUBMITTED), start=1):
            self.transaction("0x" + f"{index:064x}", status)
            self.transaction(None, status)
        self.transaction(hours=1)
        before = self.stored_transactions()

        first = TransactionMonitorService.cleanup_stale_transactions()
        second = TransactionMonitorService.cleanup_stale_transactions()

        self.assertEqual(self.stored_transactions(), before)
        self.assertEqual(first, {"cleaned": 0, "overdue": 4})
        self.assertEqual(second, first)

    def test_late_receipt_is_confirmed_after_legacy_cleanup_and_a_missing_receipt(self):
        tx = self.transaction()
        client = Mock(spec=["get_transaction_receipt"])
        client.get_transaction_receipt.side_effect = [None, CONFIRMED_RECEIPT]

        with patch("integrations.base_chain.get_base_chain_client", return_value=client):
            cleanup_failed_transactions(timestamp=0)
            missing = check_pending_transactions(timestamp=0)
            tx.refresh_from_db()
            self.assertEqual(tx.status, TransactionStatus.SUBMITTED)
            self.assertEqual(missing, {"checked": 1, "confirmed": 0, "failed": 0})

            cleanup_failed_transactions(timestamp=0)
            result = check_pending_transactions(timestamp=0)

        self.assertEqual(client.get_transaction_receipt.call_args_list, [call(tx.tx_hash), call(tx.tx_hash)])
        self.assertEqual(result, {"checked": 1, "confirmed": 1, "failed": 0})
        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.CONFIRMED)
        self.assertEqual((tx.block_number, tx.block_hash, tx.gas_used), (77, BLOCK_HASH, 21000))
        self.assertIsNotNone(tx.confirmed_at)

    def test_missing_receipt_and_provider_error_leave_overdue_state_unchanged(self):
        tx = self.transaction()
        before = self.stored_transactions()
        client = Mock(spec=["get_transaction_receipt"])
        client.get_transaction_receipt.side_effect = [None, RuntimeError("Synthetic provider outage")]

        for _ in range(2):
            TransactionMonitorService.cleanup_stale_transactions()
            TransactionMonitorService.check_pending_transactions(client)
            self.assertEqual(self.stored_transactions(), before)

        self.assertEqual(client.get_transaction_receipt.call_args_list, [call(tx.tx_hash), call(tx.tx_hash)])

    def test_an_explicit_late_revert_still_finishes_the_recorded_transaction(self):
        tx = self.transaction()
        client = Mock(spec=["get_transaction_receipt"])
        client.get_transaction_receipt.return_value = {**CONFIRMED_RECEIPT, "status": 0}

        result = TransactionMonitorService.check_pending_transactions(client)

        self.assertEqual(result, {"checked": 1, "confirmed": 0, "failed": 1})
        tx.refresh_from_db()
        self.assertEqual(tx.status, TransactionStatus.REVERTED)
        self.assertEqual(tx.error_message, "Transaction reverted on-chain")
        self.assertEqual(
            TransactionMonitorService.check_pending_transactions(client),
            {"checked": 0, "confirmed": 0, "failed": 0},
        )
        client.get_transaction_receipt.assert_called_once_with(tx.tx_hash)

    def test_cleanup_and_receipt_sweep_leave_terminal_history_unchanged(self):
        for index, status in enumerate(
            (TransactionStatus.CONFIRMED, TransactionStatus.FAILED, TransactionStatus.REVERTED), start=1
        ):
            self.transaction("0x" + f"{index:064x}", status)
        before = self.stored_transactions()
        client = Mock(spec=["get_transaction_receipt"])

        report = cleanup_failed_transactions(timestamp=0)
        checked = TransactionMonitorService.check_pending_transactions(client)

        self.assertEqual(self.stored_transactions(), before)
        self.assertEqual(report["cleaned"], 0)
        self.assertEqual(checked, {"checked": 0, "confirmed": 0, "failed": 0})
        client.get_transaction_receipt.assert_not_called()
