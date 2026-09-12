from unittest.mock import Mock, patch

from django.conf import settings
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from blockchain.models import BlockchainTransaction, TransactionStatus
from integrations.base_chain.exceptions import GasEstimationError
from shared.tests.tenants import make_tenant
from tokens.exceptions import SwapExecutionException
from tokens.models import SwapOrder
from tokens.models.choices import SwapOrderStatus
from tokens.services import AtomicSwapService

CONTRACT = "0x" + "9d" * 20
CONFIRMED = {"status": 1, "blockNumber": 7, "blockHash": "0xb", "gasUsed": 21000}
REVERTED = {"status": 0, "blockNumber": 8, "blockHash": "0xc", "gasUsed": 500000}
RPC_URL = "https://base-sepolia.g.alchemy.com/v2/pR3t3nd1ngT0B3aReAlK3y"
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
        client.assert_expected_chain = Mock(return_value=settings.BLOCKCHAIN_CHAIN_ID)
        client.to_checksum_address.side_effect = lambda address: address
        client.build_transaction.return_value = {}
        client.sign_transaction.return_value = b"signed"
        client.wait_for_receipt.side_effect = AssertionError("the swap must read the receipt, not ask for a verdict")
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
        client.receipt_even_if_reverted.side_effect = TimeoutError("receipt timed out")

        self.assertEqual(self.service(client).execute_swap(self.swap), "0xsent")

        self.assertEqual(self.status(), SwapOrderStatus.EXECUTING)
        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.SUBMITTED, "0xsent"))

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_confirmed_receipt_completes_the_swap(self, _call, _balances):
        client = self.chain_client()
        client.send_raw_transaction.return_value = "0xdone"
        client.receipt_even_if_reverted.return_value = CONFIRMED

        self.service(client).execute_swap(self.swap)

        self.assertEqual(self.status(), SwapOrderStatus.COMPLETED)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_swap_the_chain_reverted_is_failed_and_moved_nothing(self, _call, _balances):
        client = self.chain_client()
        client.send_raw_transaction.return_value = "0xreverted"
        client.receipt_even_if_reverted.return_value = REVERTED

        self.assertEqual(self.service(client).execute_swap(self.swap), "0xreverted")

        self.assertEqual(self.status(), SwapOrderStatus.FAILED)
        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.REVERTED, "0xreverted"))
        self.assertIn("0xreverted", record.error_message)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_revert_and_an_unknown_receipt_do_not_land_in_the_same_state(self, _call, _balances):
        reverted = self.chain_client()
        reverted.send_raw_transaction.return_value = "0xreverted"
        reverted.receipt_even_if_reverted.return_value = REVERTED
        self.service(reverted).execute_swap(self.swap)
        after_revert = self.status()

        self.swap = make_tenant("other-outcome").swap
        SwapOrder.objects.filter(pk=self.swap.pk).update(
            status=SwapOrderStatus.READY, seller_signature=SIGNATURE, buyer_signature=SIGNATURE
        )
        self.swap.refresh_from_db()
        silent = self.chain_client()
        silent.send_raw_transaction.return_value = "0xsilent"
        silent.receipt_even_if_reverted.side_effect = TimeoutError("no receipt")
        self.service(silent).execute_swap(self.swap)

        self.assertEqual(after_revert, SwapOrderStatus.FAILED)
        self.assertEqual(self.status(), SwapOrderStatus.EXECUTING)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_the_parties_are_told_why_without_being_told_the_node_credentials(self, _call, _balances):
        client = self.chain_client()
        client.build_transaction.side_effect = ConnectionError(
            f"HTTPSConnectionPool(host='base-sepolia.g.alchemy.com', port=443): "
            f"Max retries exceeded with url: {RPC_URL}"
        )

        with self.assertRaises(SwapExecutionException) as refusal:
            self.service(client).execute_swap(self.swap)

        self.swap.refresh_from_db()
        served = [self.swap.error_message, str(refusal.exception)]
        for order in (self.swap.sell_order, self.swap.buy_order):
            order.refresh_from_db()
            served.append(order.error_message)

        for message in served:
            self.assertNotIn("pR3t3nd1ngT0B3aReAlK3y", message)
            self.assertNotIn("alchemy.com", message)
        self.assertEqual(self.swap.error_message, "Swap execution failed")

        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertIn("pR3t3nd1ngT0B3aReAlK3y", record.error_message)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_revert_reason_the_parties_can_act_on_still_reaches_them(self, _call, _balances):
        client = self.chain_client()
        client.build_transaction.side_effect = ValueError("execution reverted: 0xdf17e316 at " + RPC_URL)

        with self.assertRaises(SwapExecutionException):
            self.service(client).execute_swap(self.swap)

        self.swap.refresh_from_db()
        self.assertEqual(self.swap.error_message, "Account is not whitelisted")
        self.assertNotIn("pR3t3nd1ngT0B3aReAlK3y", self.swap.error_message)

    @patch.object(AtomicSwapService, "validate_swap_balances")
    @patch.object(AtomicSwapService, "_execute_swap_call")
    def test_a_swap_the_node_says_will_revert_is_never_sent(self, _call, _balances):
        client = self.chain_client()
        client.build_transaction.side_effect = GasEstimationError("execution reverted: 0xdf17e316")

        with self.assertRaises(SwapExecutionException):
            self.service(client).execute_swap(self.swap)

        self.assertEqual(self.status(), SwapOrderStatus.FAILED)
        client.send_raw_transaction.assert_not_called()
        record = BlockchainTransaction.objects.get(related_uuid=self.swap.uuid)
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.FAILED, None))

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
