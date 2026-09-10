from unittest.mock import patch

from django.db import connections
from django.test import TransactionTestCase

from blockchain.models import BlockchainTransaction
from blockchain.tests.monitor_fixtures import RECEIPT, stored, sweep, transaction
from shared.db import OPERATOR_ALIAS, current_alias, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection


class ScopedMonitorObservationsTest(RunsOnTheScopedConnection, TransactionTestCase):
    def test_the_task_fetches_outside_the_operator_transaction_and_locks_its_operator_row(self):
        calls = []
        method = BlockchainTransaction.mark_confirmed

        def observe(requested_hash):
            calls.append(("rpc", current_alias(), connections[current_alias()].in_atomic_block))
            return RECEIPT

        def write(current, *args, **kwargs):
            calls.append(("write", current._state.db, connections[current_alias()].in_atomic_block))
            return method(current, *args, **kwargs)

        with use_operator():
            tx = transaction()
            with patch.object(BlockchainTransaction, "mark_confirmed", write):
                self.assertEqual(sweep(observe), {"checked": 1, "confirmed": 1, "failed": 0})
            self.assertEqual(stored(tx)["status"], "confirmed")
        self.assertEqual(calls, [("rpc", OPERATOR_ALIAS, False), ("write", OPERATOR_ALIAS, True)])

    def test_an_exception_after_the_write_rolls_back_the_operator_observation(self):
        calls = []
        method = BlockchainTransaction.mark_reverted

        def write_then_raise(current, *args, **kwargs):
            method(current, *args, **kwargs)
            calls.append((current._state.db, stored(current)["status"]))
            raise RuntimeError("Synthetic failure before commit")

        with use_operator():
            tx = transaction()
            before = stored(tx)
            with patch.object(BlockchainTransaction, "mark_reverted", write_then_raise):
                self.assertEqual(sweep({**RECEIPT, "status": 0}), {"checked": 0, "confirmed": 0, "failed": 0})
            self.assertEqual(stored(tx), before)
        self.assertEqual(calls, [(OPERATOR_ALIAS, "reverted")])
