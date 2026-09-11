from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase

from tokens.tests import test_swap_process_concurrency as workers

QUERY = "SELECT * FROM tokens_transferorder FOR UPDATE"


class RowLockObservationPollingTest(SimpleTestCase):
    def run_observations(self, observations, times):
        cursor = Mock()
        cursor.fetchone.side_effect = observations
        context = MagicMock()
        context.__enter__.return_value = cursor
        with (
            patch.object(workers, "connection", SimpleNamespace(cursor=Mock(return_value=context))),
            patch.object(workers.time, "monotonic", side_effect=times),
            patch.object(workers.time, "sleep") as sleep,
        ):
            workers.SwapWorkersUseOneCurrentClaimTest.wait_for_row_lock(
                self, SimpleNamespace(database_pid=31), "tokens_transferorder", 17
            )
        return cursor.fetchone.call_count, sleep.call_count

    def test_partial_activity_samples_are_retried_until_all_required_evidence_agrees(self):
        observations = [("BEGIN", True, None), (QUERY, True, None), (QUERY, True, "Lock")]
        self.assertEqual(self.run_observations(observations, [0, 1, 2, 3]), (3, 2))

    def test_incomplete_evidence_still_fails_at_the_original_deadline(self):
        for observed in (
            None,
            ("BEGIN", True, "Lock"),
            (QUERY, False, "Lock"),
            ("SELECT * FROM tokens_swaporder FOR UPDATE", True, "Lock"),
            ("UPDATE tokens_transferorder SET filled_quantity = 0", True, "Lock"),
            (QUERY, True, None),
        ):
            with self.subTest(observed=observed):
                with self.assertRaisesRegex(
                    AssertionError, "Worker never waited for the held tokens_transferorder row"
                ):
                    self.run_observations([observed], [0, 1, 11])

    def test_complete_evidence_returns_without_another_poll(self):
        self.assertEqual(self.run_observations([(QUERY, True, "Lock")], [0, 1]), (1, 0))
