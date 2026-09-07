from unittest.mock import Mock, patch

from django.db import transaction
from django.test import TransactionTestCase, override_settings

from blockchain.models import BlockchainTransaction, TransactionStatus
from shared.tests.tenants import make_tenant
from tokens.exceptions import SwapExecutionException
from tokens.models import SwapOrder
from tokens.models.choices import SwapOrderStatus
from tokens.services import AtomicSwapService

CONTRACT = "0x" + "9d" * 20
SIGNATURE = "0x" + "ab" * 65


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class SwapExecutionRecordsItsOutcomeTest(TransactionTestCase):

    def setUp(self):
        self.tenant = make_tenant("swapper")
        self.swap = self.tenant.swap
        SwapOrder.objects.filter(pk=self.swap.pk).update(
            status=SwapOrderStatus.READY, seller_signature=SIGNATURE, buyer_signature=SIGNATURE
        )
        self.swap.refresh_from_db()

    def service(self, client):
        with patch("tokens.services.atomic_swap_service.get_base_chain_client", return_value=client), patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            service = AtomicSwapService()
        service.chain_client = client
        return service

    @staticmethod
    def chain_client():
        client = Mock()
        client.to_checksum_address.side_effect = lambda address: address
        client.build_transaction.return_value = {}
        client.sign_transaction.return_value = b"signed"
        return client

    def status(self):
        self.swap.refresh_from_db()
        return self.swap.status

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_broadcast_that_never_answers_leaves_the_swap_executing(self, _call, _balances):
        client = self.chain_client()
        client.send_raw_transaction.side_effect = TimeoutError("no response")

        with self.assertRaises(SwapExecutionException):
            self.service(client).execute_swap(self.swap)

        self.assertEqual(self.status(), SwapOrderStatus.EXECUTING)
        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertEqual(record.status, TransactionStatus.PENDING)
        self.assertIsNone(record.tx_hash)
        self.assertIn("no response", record.error_message)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_rejection_before_broadcast_is_failed_and_says_why(self, _call, _balances):
        client = self.chain_client()
        client.sign_transaction.side_effect = ValueError("nonce too low")

        with self.assertRaises(SwapExecutionException):
            self.service(client).execute_swap(self.swap)

        self.assertEqual(self.status(), SwapOrderStatus.FAILED)
        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertEqual(record.status, TransactionStatus.FAILED)
        self.assertIn("nonce too low", record.error_message)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_broadcast_whose_receipt_never_arrives_keeps_its_hash(self, _call, _balances):
        client = self.chain_client()
        client.send_raw_transaction.return_value = "0xsent"
        client.wait_for_receipt.side_effect = TimeoutError("receipt timed out")

        self.assertEqual(self.service(client).execute_swap(self.swap), "0xsent")

        self.assertEqual(self.status(), SwapOrderStatus.EXECUTING)
        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.SUBMITTED, "0xsent"))

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_confirmed_receipt_completes_the_swap(self, _call, _balances):
        client = self.chain_client()
        client.send_raw_transaction.return_value = "0xdone"
        client.wait_for_receipt.return_value = {"status": 1, "blockNumber": 7, "blockHash": "0xb", "gasUsed": 21000}

        self.service(client).execute_swap(self.swap)

        self.assertEqual(self.status(), SwapOrderStatus.COMPLETED)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_caller_that_wraps_execution_in_a_transaction_is_refused(self, _call, _balances):
        client = self.chain_client()
        client.send_raw_transaction.return_value = "0xsent"

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.service(client).execute_swap(self.swap)

        client.send_raw_transaction.assert_not_called()
        self.assertEqual(self.status(), SwapOrderStatus.READY)
