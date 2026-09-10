from datetime import UTC, datetime
from unittest import skipUnless

from django.db import connection
from django.test import TransactionTestCase, override_settings

from shared.db import atomic
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder
from tokens.services.swap_expiry import expire_unclaimed_swap
from tokens.services.trading_locks import lock_orders
from tokens.tests import test_swap_process_concurrency as workers
from tokens.tests.swap_state_fixtures import CONTRACT, TX_HASH, persisted_outcome
from tokens.tests.test_swap_expiry import ExpiryFixtures


@skipUnless(connection.vendor == "postgresql", "Requires independent PostgreSQL row locks")
@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class ExpiryProcessesRespectExecutionClaimsTest(ExpiryFixtures, TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.now = datetime.now(UTC)
        self.clock.return_value = self.now

    def wait_for_row_lock(self, child, table, blocker_pid=None):
        workers.SwapWorkersUseOneCurrentClaimTest.wait_for_row_lock(self, child, table, blocker_pid)

    def test_two_expiry_workers_wait_for_orders_and_release_once(self):
        swap = self.matched_swap(signed="both")
        cutoff = self.expired_at(swap).isoformat()
        first = workers.SwapProcess(self, "expire", swap.pk, cutoff)
        second = workers.SwapProcess(self, "expire", swap.pk, cutoff)
        with atomic():
            lock_orders(TransferOrder.objects.filter(pk__in=[swap.sell_order_id, swap.buy_order_id]))
            for worker, blocker in ((first, None), (second, first.database_pid)):
                worker.send("run")
                worker.receive("expiring")
                self.wait_for_row_lock(worker, "tokens_transferorder", blocker)
        outcomes = [first.done()["result"], second.done()["result"]]
        self.assertEqual(sorted(outcomes), [False, True])
        self.assert_available(swap, 20)

    def test_claim_wins_before_expiry_and_remains_reserved_before_any_send(self):
        swap = self.matched_swap(signed="both")
        executor = workers.SwapProcess(self, "execute_overlap", swap.pk)
        expiry = workers.SwapProcess(self, "expire", swap.pk, self.expired_at(swap).isoformat())
        executor.send("run")
        self.assertTrue(executor.receive("claim_locked")["in_atomic"])
        expiry.send("run")
        expiry.receive("expiring")
        self.wait_for_row_lock(expiry, "tokens_swaporder", executor.database_pid)
        executor.send("claim")
        self.assertFalse(executor.receive("prepare")["in_atomic"])
        self.assertFalse(expiry.done()["result"])
        current = SwapOrder.objects.get(pk=swap.pk)
        self.assertEqual(current.status, SwapOrderStatus.EXECUTING)
        self.assertIsNotNone(current.transaction_id)
        self.assertFalse(current.transaction.tx_hash)
        self.assertEqual(current.sell_order.filled_quantity, 30)
        executor.send("prepare")
        self.assertFalse(executor.receive("sign")["in_atomic"])
        self.assertFalse(executor.receive("send")["in_atomic"])
        self.assertEqual(executor.done()["result"], TX_HASH)

    def test_expiry_wins_and_an_executor_with_an_old_ready_snapshot_cannot_send(self):
        swap = self.matched_swap(signed="both")
        executor = workers.SwapProcess(self, "execute", swap.pk)
        self.assertTrue(expire_unclaimed_swap(swap, self.expired_at(swap)))
        before = persisted_outcome(swap)
        executor.send("run")
        self.assertEqual(executor.done().get("refused"), "SwapNotReadyException")
        self.assertEqual(persisted_outcome(swap), before)
        self.assert_available(swap, 20)
