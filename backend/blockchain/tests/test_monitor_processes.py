import json
import os
import select
import subprocess
import sys
import tempfile
import time
import weakref
from unittest import skipUnless

from django.db import connections
from django.test import TransactionTestCase

from blockchain.models import BlockchainTransaction
from blockchain.tests.monitor_fixtures import (
    OTHER_HASH,
    RECEIPT,
    TX_HASH,
    stored,
    sweep,
    transaction,
)
from shared.db import atomic, current_alias


class MonitorProcess:
    def __init__(self, test, status, mode="observe"):
        self._test = weakref.ref(test)
        self.closed = False
        self.errors = tempfile.TemporaryFile()
        database = connections[current_alias()].settings_dict
        self.process = subprocess.Popen(
            [sys.executable, "-m", "blockchain.tests.monitor_worker", str(status), mode],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            bufsize=0,
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "ledova_backend.settings.test_postgres",
                "MONITOR_TEST_DATABASE": json.dumps(database, default=str),
            },
        )
        test.addCleanup(self.close)
        loaded = self.receive("loaded")
        test.assertNotEqual(loaded["pid"], os.getpid())
        test.assertEqual(loaded["alias"], "operator")
        self.database_pid = loaded["database_pid"]

    @property
    def test(self):
        test = self._test()
        if test is None:
            raise RuntimeError("Monitor testcase is no longer available")
        return test

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def error_output(self):
        self.errors.seek(0)
        return self.errors.read().decode()[-5000:]

    def receive(self, stage):
        readable, _, _ = select.select([self.process.stdout], [], [], 25)
        self.test.assertTrue(readable, f"Worker did not reach {stage}: {self.error_output()}")
        line = self.process.stdout.readline()
        self.test.assertTrue(line, self.error_output())
        event = json.loads(line)
        self.test.assertEqual(event["stage"], stage, (event, self.error_output()))
        return event

    def send(self, value):
        self.process.stdin.write((value + "\n").encode())
        self.process.stdin.flush()

    def observed(self, expected_hash=TX_HASH):
        self.send("run")
        observation = self.receive("observed")
        self.test.assertEqual(observation["requested_hash"], expected_hash)
        self.test.assertFalse(observation["in_atomic"])

    def done(self):
        result = self.receive("done")
        self.test.assertEqual(self.process.wait(timeout=10), 0, self.error_output())
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()
        self.errors.close()


@skipUnless(connections[current_alias()].vendor == "postgresql", "Independent monitor observations require row locks")
class MonitorProcessesTest(TransactionTestCase):
    def setUp(self):
        self.tx = transaction()

    def wait_for_row_lock(self, child, blocker_pid=None):
        deadline = time.monotonic() + 10
        observed = None
        while time.monotonic() < deadline:
            with connections[current_alias()].cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT query, COALESCE(%s, pg_backend_pid()) = ANY(pg_blocking_pids(pid)), wait_event_type "
                    "FROM pg_stat_activity WHERE pid = %s",
                    [blocker_pid, child.database_pid],
                )
                observed = cursor.fetchone()
            if observed and observed[1] and observed[2] == "Lock":
                self.assertTrue(observed[0].startswith("SELECT "), observed)
                self.assertIn('"blockchain_blockchaintransaction"', observed[0])
                return
            time.sleep(0.01)
        self.fail(f"Monitor never waited for the current transaction row: {observed}")

    def test_overlapping_duplicate_and_opposite_receipts_write_only_the_first_terminal_observation(self):
        original = stored(self.tx)
        for first_status, second_status in ((1, 1), (0, 0), (1, 0), (0, 1)):
            with self.subTest(first=first_status, second=second_status):
                BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**original)
                with MonitorProcess(self, first_status, "overlap") as first, MonitorProcess(
                    self, second_status
                ) as second:
                    first.observed()
                    second.observed()
                    with atomic():
                        self.assertEqual(
                            BlockchainTransaction.objects.select_for_update(nowait=True).get(pk=self.tx.pk).status,
                            "submitted",
                        )
                    first.send("apply")
                    self.assertEqual(
                        first.receive("locked"), {"stage": "locked", "in_atomic": True, "status": "submitted"}
                    )
                    second.send("apply")
                    try:
                        self.wait_for_row_lock(second, first.database_pid)
                    finally:
                        first.send("commit")
                    first_done = first.done()
                    second_done = second.done()
                    self.assertEqual(
                        first_done["result"], {"checked": 1, "confirmed": first_status, "failed": 1 - first_status}
                    )
                    self.assertEqual(second_done["result"], {"checked": 1, "confirmed": 0, "failed": 0})
                    self.assertEqual(second_done["stored"], first_done["stored"])
                    self.assertEqual(stored(self.tx)["status"], "confirmed" if first_status else "reverted")

    def test_waiting_success_and_revert_reread_a_new_terminal_decision(self):
        original = stored(self.tx)
        for receipt_status, terminal in ((1, "reverted"), (0, "confirmed"), (1, "failed"), (0, "failed")):
            with self.subTest(receipt=receipt_status, terminal=terminal):
                BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**original)
                with MonitorProcess(self, receipt_status) as child:
                    child.observed()
                    with atomic():
                        current = BlockchainTransaction.objects.select_for_update().get(pk=self.tx.pk)
                        if terminal == "confirmed":
                            current.mark_confirmed(99, OTHER_HASH, 12345)
                        elif terminal == "reverted":
                            current.mark_reverted("Earlier revert")
                        else:
                            current.mark_failed("Earlier failure")
                        before = stored(current)
                        child.send("apply")
                        self.wait_for_row_lock(child)
                    self.assertEqual(child.done()["result"], {"checked": 1, "confirmed": 0, "failed": 0})
                    self.assertEqual(stored(self.tx), before)

    def test_waiting_receipts_reread_changed_hash_and_business_reference_before_writing(self):
        original = stored(self.tx)
        for change in ({"tx_hash": OTHER_HASH}, {"related_model": "synthetic.RepointedIntent"}):
            for status in (0, 1):
                with self.subTest(change=change, status=status):
                    BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**original)
                    with MonitorProcess(self, status) as child:
                        child.observed()
                        with atomic():
                            BlockchainTransaction.objects.select_for_update().get(pk=self.tx.pk)
                            BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**change)
                            before = stored(self.tx)
                            child.send("apply")
                            self.wait_for_row_lock(child)
                        self.assertEqual(child.done()["result"], {"checked": 1, "confirmed": 0, "failed": 0})
                        self.assertEqual(stored(self.tx), before)
                        self.assertEqual(
                            sweep({**RECEIPT, "transactionHash": before["tx_hash"], "status": status}),
                            {"checked": 1, "confirmed": status, "failed": 1 - status},
                        )
