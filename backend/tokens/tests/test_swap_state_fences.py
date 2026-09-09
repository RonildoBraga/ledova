from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from eth_account.messages import encode_typed_data
from web3.datastructures import AttributeDict

from blockchain.models import BlockchainTransaction, TransactionStatus
from tokens.exceptions import (
    SwapExpiredException,
    SwapNotReadyException,
    SwapSignatureException,
)
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder, TransferOrderStatus
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONFIRMED,
    CONTRACT,
    OTHER_HASH,
    REVERTED,
    SELLER,
    TX_HASH,
    attach_claim,
    make_swap,
    persisted_outcome,
    swap_service,
    transaction_for,
)


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
@patch("tokens.services.atomic_swap_service.publish_trading_event")
class SwapSignaturesUseTheFreshStateTest(TestCase):

    def setUp(self):
        self.swap = make_swap("signature-fence")
        self.service = swap_service()
        signable = encode_typed_data(full_message=self.service.get_typed_data(self.swap))
        self.seller_signature = SELLER.sign_message(signable).signature.hex()
        self.buyer_signature = BUYER.sign_message(signable).signature.hex()

    def test_two_old_unsigned_instances_preserve_both_signatures_and_become_ready(self, _publish):
        stale = SwapOrder.objects.get(pk=self.swap.pk)
        self.service.submit_signature(self.swap, self.seller_signature, SELLER.address)
        ready = self.service.submit_signature(stale, self.buyer_signature, BUYER.address)
        self.assertEqual(ready.status, SwapOrderStatus.READY)
        self.assertEqual((ready.seller_signature, ready.buyer_signature), (self.seller_signature, self.buyer_signature))

    def test_a_missing_signature_cannot_reopen_executing_or_terminal_history(self, _publish):
        for status in (SwapOrderStatus.EXECUTING, SwapOrderStatus.COMPLETED, SwapOrderStatus.FAILED):
            SwapOrder.objects.filter(pk=self.swap.pk).update(status=status)
            before = persisted_outcome(self.swap)
            with self.subTest(status=status), self.assertRaises(SwapNotReadyException):
                self.service.submit_signature(self.swap, self.seller_signature, SELLER.address)
            self.assertEqual(persisted_outcome(self.swap), before)

    def test_an_exact_repeat_preserves_terminal_state_and_timestamps(self, _publish):
        self.service.submit_signature(self.swap, self.seller_signature, SELLER.address)
        SwapOrder.objects.filter(pk=self.swap.pk).update(status=SwapOrderStatus.COMPLETED, completed_at=timezone.now())
        before = persisted_outcome(self.swap)
        self.service.submit_signature(self.swap, self.seller_signature, SELLER.address)
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_terms_changed_during_verification_are_not_signed(self, _publish):
        verify = self.service.verify_signature

        def change(*args):
            valid = verify(*args)
            SwapOrder.objects.filter(pk=self.swap.pk).update(share_amount=self.swap.share_amount + 1)
            return valid

        self.service.verify_signature = change
        with self.assertRaises(SwapSignatureException):
            self.service.submit_signature(self.swap, self.seller_signature, SELLER.address)
        self.swap.refresh_from_db()
        self.assertEqual(self.swap.seller_signature, "")


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
@patch("tokens.services.atomic_swap_service.publish_trading_event")
class ReceiptUpdatesBelongToOneCurrentClaimTest(TestCase):

    def setUp(self):
        self.swap = make_swap("outcome-fence", ready=True)
        self.transaction = attach_claim(self.swap)
        self.service = swap_service()

    def receipt(self, receipt):
        return self.service._record_receipt(self.swap, self.transaction, TX_HASH, receipt)

    def test_matching_receipts_settle_once_without_double_unwinding(self, _publish):
        self.assertEqual(self.receipt(REVERTED), "reverted")
        after = persisted_outcome(self.swap)
        self.assertEqual([row["filled_quantity"] for row in after[2]], [20, 20])
        self.assertIsNone(self.receipt(REVERTED))
        self.assertEqual(persisted_outcome(self.swap), after)

    def test_a_web3_receipt_mapping_is_an_attributable_outcome(self, _publish):
        self.assertEqual(self.receipt(AttributeDict(CONFIRMED)), "executed")
        self.swap.refresh_from_db()
        self.assertEqual(self.swap.status, SwapOrderStatus.COMPLETED)

    def test_a_stale_transaction_uuid_cannot_apply_either_outcome(self, _publish):
        BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(tx_hash=OTHER_HASH)
        newer = transaction_for(self.swap, TX_HASH)
        SwapOrder.objects.filter(pk=self.swap.pk).update(transaction=newer)
        before = persisted_outcome(self.swap)
        for receipt in (CONFIRMED, REVERTED):
            self.assertIsNone(self.receipt(receipt))
            self.assertEqual(persisted_outcome(self.swap), before)

    def test_a_stale_unknown_fate_note_cannot_overwrite_the_current_claim(self, _publish):
        BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(tx_hash=OTHER_HASH)
        newer = transaction_for(self.swap, TX_HASH)
        SwapOrder.objects.filter(pk=self.swap.pk).update(transaction=newer)
        before = persisted_outcome(self.swap)
        self.service._record_unknown_fate(self.swap, self.transaction, "old worker failed")
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_a_stale_local_failure_cannot_release_a_new_hashless_claim(self, _publish):
        BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(
            tx_hash=None, status=TransactionStatus.PENDING
        )
        SwapOrder.objects.filter(pk=self.swap.pk).update(tx_hash="")
        self.swap.refresh_from_db()
        self.transaction.refresh_from_db()
        newer = transaction_for(self.swap, None, TransactionStatus.PENDING)
        SwapOrder.objects.filter(pk=self.swap.pk).update(transaction=newer)
        before = persisted_outcome(self.swap)
        self.service._record_never_sent(self.swap, self.transaction, "old local rejection", "old local rejection")
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_a_stale_hash_with_the_same_uuid_cannot_apply_either_outcome(self, _publish):
        BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(tx_hash=OTHER_HASH)
        SwapOrder.objects.filter(pk=self.swap.pk).update(tx_hash=OTHER_HASH)
        before = persisted_outcome(self.swap)
        for receipt in (CONFIRMED, REVERTED):
            self.assertIsNone(self.receipt(receipt))
            self.assertEqual(persisted_outcome(self.swap), before)

    def test_disagreeing_recorded_hashes_are_not_a_current_receipt_identity(self, _publish):
        BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(tx_hash=OTHER_HASH)
        self.transaction.refresh_from_db()
        before = persisted_outcome(self.swap)
        self.assertIsNone(self.receipt(CONFIRMED))
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_a_receipt_cannot_ignore_a_different_recorded_swap_hash(self, _publish):
        SwapOrder.objects.filter(pk=self.swap.pk).update(tx_hash=OTHER_HASH)
        self.swap.refresh_from_db()
        before = persisted_outcome(self.swap)
        self.assertIsNone(self.receipt(CONFIRMED))
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_opposite_terminal_transaction_evidence_is_not_overwritten(self, _publish):
        for state, receipt in ((TransactionStatus.CONFIRMED, REVERTED), (TransactionStatus.REVERTED, CONFIRMED)):
            BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(status=state)
            before = persisted_outcome(self.swap)
            self.assertIsNone(self.receipt(receipt))
            self.assertEqual(persisted_outcome(self.swap), before)

    def test_matching_terminal_transaction_evidence_can_complete_the_swap_without_rewriting_it(self, _publish):
        self.transaction.mark_confirmed(99, OTHER_HASH, 12345)
        before = BlockchainTransaction.objects.filter(pk=self.transaction.pk).values().get()
        self.assertEqual(self.receipt(CONFIRMED), "executed")
        self.assertEqual(BlockchainTransaction.objects.filter(pk=self.transaction.pk).values().get(), before)
        self.swap.refresh_from_db()
        self.assertEqual(self.swap.status, SwapOrderStatus.COMPLETED)

    def test_a_late_success_cannot_reopen_a_cancelled_order_after_failure(self, _publish):
        self.receipt(REVERTED)
        order = TransferOrder.objects.get(pk=self.swap.sell_order_id)
        order.cancel()
        before = persisted_outcome(self.swap)
        self.assertIsNone(self.receipt(CONFIRMED))
        self.assertEqual(persisted_outcome(self.swap), before)
        order.refresh_from_db()
        self.assertEqual(order.status, TransferOrderStatus.CANCELLED)

    def test_missing_status_or_a_different_receipt_hash_is_not_a_revert(self, _publish):
        before = persisted_outcome(self.swap)
        for receipt in (None, {}, {"status": None}, {"status": 2}, {**REVERTED, "transactionHash": OTHER_HASH}):
            self.assertIsNone(self.receipt(receipt))
            self.assertEqual(persisted_outcome(self.swap), before)

    def test_an_expired_send_and_generic_monitor_failure_remain_reserved_without_a_receipt(self, _publish):
        SwapOrder.objects.filter(pk=self.swap.pk).update(expires_at=timezone.now() - timedelta(days=1))
        BlockchainTransaction.objects.filter(pk=self.transaction.pk).update(
            status=TransactionStatus.FAILED, error_message="Transaction timed out after 24 hours"
        )
        self.swap.refresh_from_db()
        self.service.chain_client.receipt_even_if_reverted.return_value = None
        before = persisted_outcome(self.swap)
        self.assertIsNone(self.service.resolve_executing_swap(self.swap))
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_a_used_nonce_without_a_recorded_hash_does_not_complete_legacy_history(self, _publish):
        SwapOrder.objects.filter(pk=self.swap.pk).update(tx_hash="", expires_at=timezone.now() - timedelta(days=1))
        self.swap.refresh_from_db()
        self.service.is_nonce_used = Mock(return_value=True)
        before = persisted_outcome(self.swap)
        self.assertFalse(self.service.chain_says_this_swap_executed(self.swap))
        self.assertIsNone(self.service.resolve_executing_swap(self.swap))
        self.assertEqual(persisted_outcome(self.swap), before)
        self.service.chain_client.receipt_even_if_reverted.assert_not_called()


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class ExecutionAdmissionUsesTheCurrentRowTest(TransactionTestCase):

    def setUp(self):
        self.swap = make_swap("claim-admission", ready=True)
        self.service = swap_service()

    def test_a_stale_ready_instance_does_not_prepare_a_second_execution(self):
        first, record = self.service._claim_execution(self.swap.pk)
        self.service.validate_swap_balances = Mock()
        self.service._prepare_attempt = Mock()
        with self.assertRaises(SwapNotReadyException):
            self.service.execute_swap(self.swap)
        self.service.validate_swap_balances.assert_not_called()
        self.service._prepare_attempt.assert_not_called()
        first.refresh_from_db()
        self.assertEqual(first.transaction_id, record.pk)
        self.assertEqual(BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).count(), 1)

    def test_ready_after_its_signed_deadline_cannot_claim(self):
        SwapOrder.objects.filter(pk=self.swap.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(SwapExpiredException):
            self.service.execute_swap(self.swap)
        self.assertFalse(BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).exists())
