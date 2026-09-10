import os
import pickle
from types import SimpleNamespace
from unittest.case import _Outcome
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.test.runner import RemoteTestResult

from blockchain.tests import test_monitor_processes as monitor


class MonitorLockObserverTest(SimpleTestCase):
    def setUp(self):
        self.case = monitor.MonitorProcessesTest(
            "test_waiting_receipts_reread_changed_hash_and_business_reference_before_writing"
        )
        self.cursor = MagicMock()
        self.child = SimpleNamespace(database_pid=1234)
        self.query = 'SELECT "blockchain_blockchaintransaction"."uuid" FROM "blockchain_blockchaintransaction"'

    def observe(self, samples, clock):
        self.cursor.fetchone.side_effect = samples
        with patch("blockchain.tests.test_monitor_processes.connections") as connections, patch(
            "blockchain.tests.test_monitor_processes.time.monotonic", side_effect=clock
        ), patch("blockchain.tests.test_monitor_processes.time.sleep") as pause:
            connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = self.cursor
            self.case.wait_for_row_lock(self.child, 5678)
        return pause

    def test_transient_missing_wait_event_waits_for_a_coherent_lock_observation(self):
        pause = self.observe([(self.query, True, None), (self.query, True, "Lock")], [0, 0, 0.01])
        pause.assert_called_once_with(0.01)
        self.assertEqual(self.cursor.fetchone.call_count, 2)
        for clear, observation in zip(
            self.cursor.execute.call_args_list[::2], self.cursor.execute.call_args_list[1::2]
        ):
            self.assertEqual(clear.args, ("SELECT pg_stat_clear_snapshot()",))
            self.assertEqual(observation.args[1], [5678, 1234])

    def test_missing_activity_and_an_unrelated_blocker_do_not_release_the_parent(self):
        self.observe([None, (self.query, False, "Lock"), (self.query, True, "Lock")], [0, 0, 0.01, 0.02])
        self.assertEqual(self.cursor.fetchone.call_count, 3)

    def test_a_blocked_update_does_not_prove_the_required_select_lock(self):
        with self.assertRaises(AssertionError):
            self.observe([('UPDATE "blockchain_blockchaintransaction" SET "status" = %s', True, "Lock")], [0, 0])

    def test_a_blocked_select_on_another_table_does_not_release_the_parent(self):
        with self.assertRaises(AssertionError):
            self.observe([('SELECT "blockchain_chain"."id" FROM "blockchain_chain"', True, "Lock")], [0, 0])

    def test_an_intended_blocker_without_a_lock_event_expires_at_the_existing_deadline(self):
        with self.assertRaisesRegex(AssertionError, "Monitor never waited for the current transaction row"):
            self.observe([(self.query, True, None)], [0, 0, 10])
        self.assertEqual(self.cursor.fetchone.call_count, 1)

    def test_a_lock_without_the_intended_blocker_expires_at_the_existing_deadline(self):
        with self.assertRaisesRegex(AssertionError, "Monitor never waited for the current transaction row"):
            self.observe([(self.query, False, "Lock")], [0, 0, 10])
        self.assertEqual(self.cursor.fetchone.call_count, 1)


class MonitorParallelReportingTest(SimpleTestCase):
    def test_a_failed_monitor_subtest_preserves_its_assertion_and_parameters_after_pickling(self):
        case = monitor.MonitorProcessesTest(
            "test_waiting_receipts_reread_changed_hash_and_business_reference_before_writing"
        )
        with patch("blockchain.tests.test_monitor_processes.transaction", return_value=None):
            case.setUp()
        result = RemoteTestResult()
        result.startTest(case)
        case._outcome = _Outcome(result)
        loaded = {"pid": os.getpid() + 1, "database_pid": 1234, "alias": "operator"}
        with patch("blockchain.tests.test_monitor_processes.subprocess.Popen") as process, patch.object(
            monitor.MonitorProcess, "receive", return_value=loaded
        ):
            process.return_value.poll.return_value = 0
            try:
                with case.subTest(change={"related_model": "synthetic.RepointedIntent"}, status=1):
                    with monitor.MonitorProcess(case, 1) as child:
                        case.fail("Synthetic monitor row-lock observation failure")
                active_events = pickle.loads(pickle.dumps(result.events))
            finally:
                case.doCleanups()
                case._outcome = None
                result.stopTest(case)

            completed_events = pickle.loads(pickle.dumps(result.events))
            for events in (active_events, completed_events):
                failures = [event for event in events if event[0] == "addSubTest"]
                self.assertEqual(len(failures), 1)
                _, index, subtest, error = failures[0]
                self.assertEqual(index, 0)
                self.assertEqual(subtest.test_case.id(), case.id())
                self.assertEqual(
                    dict(subtest.params), {"change": {"related_model": "synthetic.RepointedIntent"}, "status": 1}
                )
                self.assertIs(error[0], AssertionError)
                self.assertEqual(str(error[1]), "Synthetic monitor row-lock observation failure")
                self.assertIsNotNone(error[2])
            self.assertTrue(child.closed)
            self.assertTrue(child.errors.closed)
            process.return_value.stdin.close.assert_called_once_with()
            process.return_value.stdout.close.assert_called_once_with()
            self.assertFalse(result.wasSuccessful())
