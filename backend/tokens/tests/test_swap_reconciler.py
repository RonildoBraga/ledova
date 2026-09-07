import inspect
from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from web3 import Web3

from shared.tests.tenants import make_tenant
from tokens.models import SwapOrder, TransferOrder
from tokens.models.choices import SwapOrderStatus, TransferOrderStatus
from tokens.services import AtomicSwapService
from tokens.tasks.swap_reconciler import STALE_EXECUTION_AGE, resolve_executing_swaps

CONTRACT = "0x" + "9d" * 20


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
@patch("tokens.services.atomic_swap_service.publish_trading_event")
class AnExecutingSwapIsAskedOfTheChainTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("stuck")
        self.swap = self.tenant.swap
        self.stale(self.swap)

    @staticmethod
    def stale(swap, status=SwapOrderStatus.EXECUTING):
        SwapOrder.objects.filter(pk=swap.pk).update(
            status=status, updated_at=timezone.now() - STALE_EXECUTION_AGE - timedelta(minutes=1)
        )
        swap.refresh_from_db()

    def expire(self):
        SwapOrder.objects.filter(pk=self.swap.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.swap.refresh_from_db()

    def service(self, nonce_used):
        with patch("tokens.services.atomic_swap_service.get_base_chain_client"), patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            service = AtomicSwapService()
        service.is_nonce_used = Mock(return_value=nonce_used)
        return service

    def status(self):
        self.swap.refresh_from_db()
        return self.swap.status

    def test_a_swap_whose_nonce_the_chain_used_is_reconciled_to_completed(self, _publish):
        self.assertEqual(self.service(True).resolve_executing_swap(self.swap), "executed")

        self.assertEqual(self.status(), SwapOrderStatus.COMPLETED)

    def test_a_swap_whose_nonce_is_unused_and_whose_deadline_has_passed_is_failed(self, _publish):
        self.expire()

        self.assertEqual(self.service(False).resolve_executing_swap(self.swap), "never executed")

        self.assertEqual(self.status(), SwapOrderStatus.FAILED)

    def test_a_swap_whose_nonce_is_unused_and_still_live_is_left_alone(self, _publish):
        self.assertIsNone(self.service(False).resolve_executing_swap(self.swap))

        self.assertEqual(self.status(), SwapOrderStatus.EXECUTING)

    def test_a_swap_that_moved_on_before_the_write_is_not_reconciled_twice(self, _publish):
        service = self.service(True)
        service.is_nonce_used = Mock(
            side_effect=lambda *_: SwapOrder.objects.filter(pk=self.swap.pk).update(status=SwapOrderStatus.COMPLETED)
            or True
        )

        self.assertIsNone(service.resolve_executing_swap(self.swap))


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class TheSweepFindsOnlyStuckSwapsTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("sweeper")
        self.swap = self.tenant.swap

    def age(self, status, minutes):
        SwapOrder.objects.filter(pk=self.swap.pk).update(
            status=status, updated_at=timezone.now() - timedelta(minutes=minutes)
        )

    @patch("tokens.tasks.swap_reconciler.AtomicSwapService")
    def test_a_swap_executing_for_longer_than_the_grace_period_is_checked(self, service_class):
        service_class.return_value.resolve_executing_swap.return_value = "executed"
        self.age(SwapOrderStatus.EXECUTING, 20)

        self.assertEqual(resolve_executing_swaps(), {"checked": 1, "resolved": 1})

    @patch("tokens.tasks.swap_reconciler.AtomicSwapService")
    def test_a_swap_that_has_just_started_executing_is_left_for_the_broadcast(self, service_class):
        self.age(SwapOrderStatus.EXECUTING, 1)

        self.assertEqual(resolve_executing_swaps(), {"checked": 0, "resolved": 0})
        service_class.assert_not_called()

    @patch("tokens.tasks.swap_reconciler.AtomicSwapService")
    def test_a_swap_in_any_other_status_is_not_swept(self, service_class):
        for status in (SwapOrderStatus.READY, SwapOrderStatus.COMPLETED, SwapOrderStatus.FAILED):
            self.age(status, 20)

            self.assertEqual(resolve_executing_swaps(), {"checked": 0, "resolved": 0}, status)

    @patch("tokens.tasks.swap_reconciler.AtomicSwapService")
    def test_one_swap_that_cannot_be_reached_does_not_stop_the_sweep(self, service_class):
        service_class.return_value.resolve_executing_swap.side_effect = RuntimeError("rpc down")
        self.age(SwapOrderStatus.EXECUTING, 20)

        self.assertEqual(resolve_executing_swaps(), {"checked": 1, "resolved": 0})


class UnwindingASwapTwiceCostsTheOrdersNothingExtraTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("unwinder")
        self.swap = self.tenant.swap
        self.filled_before = self.swap.share_amount * 3
        TransferOrder.objects.filter(pk__in=[self.swap.sell_order_id, self.swap.buy_order_id]).update(
            quantity=self.filled_before, filled_quantity=self.filled_before, status=TransferOrderStatus.MATCHED
        )
        self.swap = SwapOrder.objects.select_related("sell_order", "buy_order").get(pk=self.swap.pk)

    def filled(self):
        return [
            TransferOrder.objects.get(pk=pk).filled_quantity for pk in (self.swap.sell_order_id, self.swap.buy_order_id)
        ]

    def test_a_second_unwind_does_not_subtract_the_share_amount_again(self):
        self.swap.mark_failed("first")
        after_one = self.filled()

        self.swap.mark_failed("second")

        self.assertEqual(after_one, [self.filled_before - self.swap.share_amount] * 2)
        self.assertEqual(self.filled(), after_one)

    def test_the_orders_start_far_enough_above_the_share_amount_for_a_second_subtraction_to_show(self):
        self.assertGreater(self.filled_before - 2 * self.swap.share_amount, 0)

    def test_the_reason_recorded_is_the_one_that_actually_failed_it(self):
        self.swap.mark_failed("the chain refused it")
        self.swap.mark_failed("a later sweep guessed")

        self.swap.refresh_from_db()
        self.assertEqual(self.swap.error_message, "the chain refused it")


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
@patch("tokens.services.atomic_swap_service.publish_trading_event")
class TheChainIsAskedOutsideEveryTransactionTest(TransactionTestCase):

    def setUp(self):
        self.tenant = make_tenant("outside")
        self.swap = self.tenant.swap
        SwapOrder.objects.filter(pk=self.swap.pk).update(status=SwapOrderStatus.EXECUTING)
        self.swap.refresh_from_db()

    def test_the_nonce_read_does_not_happen_inside_an_open_transaction(self, _publish):
        with patch("tokens.services.atomic_swap_service.get_base_chain_client"), patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            service = AtomicSwapService()
        seen = []
        service.is_nonce_used = Mock(
            side_effect=lambda *_: seen.append(transaction.get_connection().in_atomic_block) or True
        )

        self.assertEqual(service.resolve_executing_swap(self.swap), "executed")

        self.assertEqual(seen, [False])


class TwoSwapsCannotShareANonceTest(TestCase):

    def test_the_database_refuses_a_second_swap_with_the_same_nonce(self):
        tenant = make_tenant("nonces")
        first = tenant.swap

        with self.assertRaises(IntegrityError):
            SwapOrder.objects.create(
                sell_order=first.sell_order,
                buy_order=first.buy_order,
                share_token=first.share_token,
                payment_asset=first.payment_asset,
                seller_address=first.seller_address,
                buyer_address=first.buyer_address,
                share_amount=first.share_amount,
                payment_amount=first.payment_amount,
                nonce=first.nonce,
                order_hash="0x" + "ab" * 32,
                expires_at=first.expires_at,
                status=SwapOrderStatus.CREATED,
            )

    def test_a_different_nonce_is_accepted_so_the_constraint_is_about_the_nonce(self):
        tenant = make_tenant("nonces-ok")
        first = tenant.swap

        second = SwapOrder.objects.create(
            sell_order=first.sell_order,
            buy_order=first.buy_order,
            share_token=first.share_token,
            payment_asset=first.payment_asset,
            seller_address=first.seller_address,
            buyer_address=first.buyer_address,
            share_amount=first.share_amount,
            payment_amount=first.payment_amount,
            nonce=first.nonce + 1,
            order_hash="0x" + "cd" * 32,
            expires_at=first.expires_at,
            status=SwapOrderStatus.CREATED,
        )

        self.assertNotEqual(second.pk, first.pk)


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
@patch("tokens.services.atomic_swap_service.publish_trading_event")
class TheReceiptMustNameThisOrderTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("receipts")
        self.swap = self.tenant.swap
        SwapOrder.objects.filter(pk=self.swap.pk).update(status=SwapOrderStatus.EXECUTING, tx_hash="0xsettled")
        self.swap.refresh_from_db()

    @staticmethod
    def hashing_service():
        with patch("tokens.services.atomic_swap_service.get_base_chain_client"), patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            service = AtomicSwapService()
        service.chain_client.chain_id = 84532
        service.chain_client.to_checksum_address.side_effect = Web3.to_checksum_address
        return service

    def service(self, events):
        service = self.hashing_service()
        service.is_nonce_used = Mock(return_value=True)
        contract = Mock()
        contract.events.SwapExecuted.return_value.process_receipt.return_value = events
        service.chain_client.load_contract.return_value = contract
        service.chain_client.receipt_even_if_reverted.return_value = {"status": 1}
        return service

    def test_a_receipt_naming_this_order_completes_the_swap(self, _publish):
        expected = self.hashing_service().executed_order_hash(self.swap)
        service = self.service([{"args": {"orderHash": bytes.fromhex(expected.lstrip("0x"))}}])

        self.assertEqual(service.resolve_executing_swap(self.swap), "executed")

    def test_a_receipt_naming_another_order_leaves_the_swap_alone(self, _publish):
        service = self.service([{"args": {"orderHash": bytes.fromhex("ee" * 32)}}])

        self.assertIsNone(service.resolve_executing_swap(self.swap))

        self.swap.refresh_from_db()
        self.assertEqual(self.swap.status, SwapOrderStatus.EXECUTING)

    def test_a_receipt_with_no_swap_event_leaves_the_swap_alone(self, _publish):
        service = self.service([])

        self.assertIsNone(service.resolve_executing_swap(self.swap))

    def test_the_hash_checked_is_the_digest_the_contract_emits_not_the_struct_hash(self, _publish):
        service = self.hashing_service()

        self.assertNotEqual(service.executed_order_hash(self.swap).lstrip("0x"), self.swap.order_hash.lstrip("0x"))


class TheNonceGeneratorDoesNotRelyOnTheConstraintTest(TestCase):

    @staticmethod
    def service():
        with patch("tokens.services.atomic_swap_service.get_base_chain_client"), patch(
            "tokens.services.atomic_swap_service.WhitelistService"
        ):
            return AtomicSwapService()

    def test_nonces_drawn_together_are_not_neighbours_around_a_shared_clock(self):
        service = self.service()

        drawn = [service._generate_nonce() for _ in range(200)]

        self.assertEqual(len(set(drawn)), len(drawn))
        self.assertGreater(max(drawn) - min(drawn), 2**40)

    def test_the_generator_reads_no_clock(self):
        source = inspect.getsource(AtomicSwapService._generate_nonce)

        self.assertNotIn("time", source)
        self.assertIn("randbits", source)
