import json
from datetime import UTC, datetime, timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from eth_account.messages import encode_typed_data

from ledova_backend.procrastinate_app import app
from shared.db import atomic
from tokens.events import publish_trading_event
from tokens.exceptions import SwapNotReadyException
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder, TransferOrderStatus
from tokens.services.swap_expiry import expire_unclaimed_swap, expire_unclaimed_swaps
from tokens.services.token_transfer_service import TokenTransferService
from tokens.tasks.swap_expiry import expire_unclaimed_matches
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONTRACT,
    SELLER,
    TX_HASH,
    make_swap,
    persisted_outcome,
    swap_service,
    transaction_for,
)
from tokens.views.trading_events import _format_public_trading_event


class ExpiryFixtures:

    def setUp(self):
        self.now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
        self.clock = self.enterContext(patch("django.utils.timezone.now", return_value=self.now))
        self.publisher = self.enterContext(patch("tokens.services.swap_expiry.publish_trading_event"))
        self.enterContext(patch("tokens.services.atomic_swap_service.publish_trading_event"))
        self.service = swap_service()
        self.counter = 0

    def matched_swap(self, *, already_filled=20, signed=""):
        self.counter += 1
        template = make_swap(f"expiry-{self.counter}")
        SwapOrder.objects.filter(pk=template.pk).delete()
        TransferOrder.objects.filter(pk__in=[template.sell_order_id, template.buy_order_id]).update(
            status=TransferOrderStatus.OPEN, filled_quantity=already_filled
        )
        with patch("tokens.services.AtomicSwapService", return_value=self.service):
            swap = object.__new__(TokenTransferService).match_orders(
                template.buy_order, template.sell_order, match_quantity=10
            )["swap_order"]
        for party, signer in (("seller", SELLER), ("buyer", BUYER)):
            if party in signed or signed == "both":
                signature = signer.sign_message(
                    encode_typed_data(full_message=self.service.get_typed_data(swap))
                ).signature.hex()
                swap = self.service.submit_signature(swap, signature, signer.address)
        return swap

    def expired_at(self, swap):
        return swap.expires_at + timedelta(seconds=1)

    def assert_available(self, swap, expected_filled):
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapOrderStatus.EXPIRED)
        for order in (swap.sell_order, swap.buy_order):
            self.assertEqual(order.filled_quantity, expected_filled)
            self.assertEqual(
                order.status, TransferOrderStatus.PARTIALLY_FILLED if expected_filled else TransferOrderStatus.OPEN
            )
            self.assertTrue(order.can_cancel)
            self.assertTrue(order.can_be_modified)


@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class UnclaimedSwapExpiryTest(ExpiryFixtures, TransactionTestCase):

    def test_each_unsigned_or_ready_match_releases_once_and_preserves_signed_terms(self):
        for signed in ("", "seller", "buyer", "both"):
            with self.subTest(signed=signed):
                swap = self.matched_swap(signed=signed)
                terms = self.service.get_typed_data(swap)
                signatures = (swap.seller_signature, swap.buyer_signature)
                self.assertTrue(swap.expiry_release_eligible)
                self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))
                self.assert_available(swap, 20)
                self.assertEqual(self.service.get_typed_data(swap), terms)
                self.assertEqual((swap.seller_signature, swap.buyer_signature), signatures)
                after = persisted_outcome(swap)
                self.assertFalse(expire_unclaimed_swap(swap, self.expired_at(swap)))
                self.assertEqual(persisted_outcome(swap), after)
        self.assertEqual(self.publisher.call_count, 4)
        self.publisher.assert_called_with("swap_expired", str(swap.share_token_id))
        self.service.chain_client.send_raw_transaction.assert_not_called()

    def test_unfilled_orders_reopen_and_can_match_again(self):
        swap = self.matched_swap(already_filled=0)
        self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))
        self.assert_available(swap, 0)
        with patch("tokens.services.AtomicSwapService", return_value=self.service):
            matched = object.__new__(TokenTransferService).match_orders(swap.buy_order, swap.sell_order, 10)
        self.assertNotEqual(matched["swap_order"].pk, swap.pk)
        self.assertEqual(matched["matched_quantity"], 10)

    def test_future_and_exact_deadline_matches_remain_reserved(self):
        swap = self.matched_swap(signed="both")
        before = persisted_outcome(swap)
        for now in (self.now, swap.expires_at):
            with self.subTest(now=now):
                self.assertFalse(expire_unclaimed_swap(swap, now))
                self.assertEqual(expire_unclaimed_swaps(now), {"checked": 0, "expired": 0, "retained": 0})
                self.assertEqual(persisted_outcome(swap), before)
        self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))

    def test_current_claim_and_hashless_uncertain_execution_are_never_released(self):
        swap = self.matched_swap(signed="both")
        claimed, transaction = self.service._claim_execution(swap.pk)
        self.assertIsNone(transaction.tx_hash)
        before = persisted_outcome(swap)
        self.assertFalse(expire_unclaimed_swap(swap, self.expired_at(swap)))
        self.assertFalse(expire_unclaimed_swap(claimed, self.expired_at(swap)))
        self.assertEqual(persisted_outcome(swap), before)
        self.assertEqual(expire_unclaimed_swaps(self.expired_at(swap))["expired"], 0)

    def test_inconsistent_history_claims_hashes_and_terminal_states_remain_untouched(self):
        for field, value in (
            ("status", SwapOrderStatus.EXECUTING),
            ("status", SwapOrderStatus.COMPLETED),
            ("status", SwapOrderStatus.FAILED),
            ("status", SwapOrderStatus.EXPIRED),
            ("tx_hash", TX_HASH),
            ("buyer_signature", "unexpected stored signature"),
            ("transaction", "orphan"),
            ("transaction", "attached"),
        ):
            with self.subTest(field=field, value=value):
                swap = self.matched_swap()
                if field == "transaction":
                    transaction = transaction_for(swap, tx_hash=None)
                    if value == "attached":
                        SwapOrder.objects.filter(pk=swap.pk).update(transaction=transaction)
                else:
                    SwapOrder.objects.filter(pk=swap.pk).update(**{field: value})
                before = persisted_outcome(swap)
                self.assertFalse(expire_unclaimed_swap(swap, self.expired_at(swap)))
                self.assertEqual(persisted_outcome(swap), before)

    def test_legacy_unsigned_and_ready_rows_cannot_be_released_from_absent_claim_data(self):
        for ready in (False, True):
            with self.subTest(ready=ready):
                swap = make_swap(f"legacy-expiry-{ready}", ready=ready)
                TransferOrder.objects.filter(pk=swap.sell_order_id).update(matched_order=swap.buy_order)
                TransferOrder.objects.filter(pk=swap.buy_order_id).update(matched_order=swap.sell_order)
                self.assertFalse(swap.expiry_release_eligible)
                before = persisted_outcome(swap)
                self.assertFalse(expire_unclaimed_swap(swap, self.expired_at(swap)))
                self.assertEqual(persisted_outcome(swap), before)
        self.assertEqual(expire_unclaimed_swaps(self.expired_at(swap))["checked"], 0)
        positive = self.matched_swap(signed="both")
        self.assertTrue(expire_unclaimed_swap(positive, self.expired_at(positive)))

    def test_previously_filled_orders_return_to_the_book_with_only_their_remaining_quantity(self):
        swap = self.matched_swap()
        orders = TransferOrder.objects.filter(pk__in=[swap.sell_order_id, swap.buy_order_id])
        for side in ("buy", "sell"):
            self.assertEqual(list(orders.order_book_levels(swap.share_token, side)), [])
        self.assertIsNone(orders.best_bid(swap.share_token))
        self.assertIsNone(orders.best_ask(swap.share_token))
        self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))
        self.assert_available(swap, 20)
        for side in ("buy", "sell"):
            levels = list(orders.order_book_levels(swap.share_token, side))
            self.assertEqual(len(levels), 1)
            self.assertEqual(levels[0]["total_quantity"], 20)
            self.assertEqual(levels[0]["order_count"], 1)
        self.assertEqual(orders.best_bid(swap.share_token).pk, swap.buy_order_id)
        self.assertEqual(orders.best_ask(swap.share_token).pk, swap.sell_order_id)

    def test_changed_order_reservations_and_additional_active_matches_are_retained(self):
        for mutation in ("quantity", "status", "counterparty", "another_swap"):
            with self.subTest(mutation=mutation):
                swap = self.matched_swap()
                orders = TransferOrder.objects.filter(pk=swap.sell_order_id)
                if mutation == "quantity":
                    orders.update(filled_quantity=9)
                elif mutation == "status":
                    orders.update(status=TransferOrderStatus.COMPLETED)
                elif mutation == "counterparty":
                    orders.update(matched_order=None)
                else:
                    other = make_swap("other-expiry")
                    SwapOrder.objects.filter(pk=other.pk).update(sell_order=swap.sell_order)
                before = persisted_outcome(swap)
                self.assertFalse(expire_unclaimed_swap(swap, self.expired_at(swap)))
                self.assertEqual(persisted_outcome(swap), before)

    def test_verified_signature_cannot_revive_an_expired_match(self):
        swap = self.matched_swap()
        signature = SELLER.sign_message(
            encode_typed_data(full_message=self.service.get_typed_data(swap))
        ).signature.hex()
        self.assertTrue(self.service.verify_signature(swap, signature, SELLER.address))
        self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))
        before = persisted_outcome(swap)
        with self.assertRaises(SwapNotReadyException):
            self.service._store_signature(swap, signature, True)
        self.assertEqual(persisted_outcome(swap), before)

    def test_task_scans_past_retained_rows_and_drains_multiple_pages(self):
        swaps = [self.matched_swap() for _ in range(4)]
        retained = min(swaps, key=lambda swap: swap.pk)
        transaction_for(retained, tx_hash=None)
        self.clock.return_value = self.expired_at(retained)
        self.assertEqual(expire_unclaimed_swaps(batch=1), {"checked": 4, "expired": 3, "retained": 1})
        for swap in swaps:
            swap.refresh_from_db()
            self.assertEqual(
                swap.status, SwapOrderStatus.CREATED if swap.pk == retained.pk else SwapOrderStatus.EXPIRED
            )
        self.assertEqual(expire_unclaimed_matches.func(), {"checked": 1, "expired": 0, "retained": 1})

    def test_a_later_failure_keeps_an_earlier_committed_release(self):
        swaps = sorted([self.matched_swap(), self.matched_swap()], key=lambda swap: swap.pk)
        real_expiry = expire_unclaimed_swap

        def fail_second(swap, cutoff):
            if swap.pk == swaps[1].pk:
                raise RuntimeError("synthetic database interruption")
            return real_expiry(swap, cutoff)

        with patch("tokens.services.swap_expiry.expire_unclaimed_swap", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "synthetic database interruption"):
                expire_unclaimed_swaps(self.expired_at(swaps[0]), batch=1)
        self.assert_available(swaps[0], 20)
        swaps[1].refresh_from_db()
        self.assertEqual(swaps[1].status, SwapOrderStatus.CREATED)

    def test_release_publishes_the_expiry_event_after_commit_without_private_identifiers(self):
        swap = self.matched_swap()
        with (
            patch("tokens.services.swap_expiry.publish_trading_event", wraps=publish_trading_event),
            patch("tokens.events._get_redis_client") as redis,
        ):
            self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))
        redis.return_value.publish.assert_called_once()
        payload = json.loads(redis.return_value.publish.call_args.args[1])
        self.assertEqual(payload, {"event": "swap_expired", "token": str(swap.share_token_id)})
        self.assertEqual(
            _format_public_trading_event(payload, str(swap.share_token_id)), "event: swap_expired\ndata: {}\n\n"
        )

    @skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL eligibility trigger")
    def test_creation_marker_cannot_be_added_to_history_or_removed_from_new_matches(self):
        old = make_swap("eligibility-history")
        new = self.matched_swap()
        for swap in (old, new):
            before = persisted_outcome(swap)
            with self.assertRaises(IntegrityError), atomic():
                SwapOrder.objects.filter(pk=swap.pk).update(expiry_release_eligible=not swap.expiry_release_eligible)
            self.assertEqual(persisted_outcome(swap), before)
        new.error_message = "Unrelated metadata remains writable"
        new.save(update_fields=["error_message"])
        new.refresh_from_db()
        self.assertEqual(new.error_message, "Unrelated metadata remains writable")


class SwapExpiryScheduleTest(SimpleTestCase):

    def test_registered_expiry_sweep_runs_every_minute(self):
        name = "tokens.tasks.swap_expiry.expire_unclaimed_matches"
        self.assertIs(app.tasks[name], expire_unclaimed_matches)
        self.assertEqual(
            [entry.cron for entry in app.periodic_registry.periodic_tasks.values() if entry.task.name == name],
            ["* * * * *"],
        )
