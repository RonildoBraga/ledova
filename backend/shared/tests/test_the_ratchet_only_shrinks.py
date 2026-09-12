import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import TestCase as PlainTestCase
from unittest import TestSuite

from django.test import SimpleTestCase

from shared.behind_the_policies_runner import (
    NOT_YET_BEHIND_THE_POLICIES,
    BehindThePoliciesRunner,
    cases_in,
    let_the_listed_ones_fail,
)


class Recorded(PlainTestCase):
    def test_one(self):
        pass

    def test_two(self):
        pass


class TheListMarksExactlyWhatItNamesTest(SimpleTestCase):

    def runner_over(self, listed):
        suite = TestSuite([Recorded("test_one"), Recorded("test_two")])
        for case in cases_in(suite):
            getattr(case, case._testMethodName).__func__.__unittest_expecting_failure__ = False
        let_the_listed_ones_fail(suite, listed)
        return {
            case.id(): getattr(case, case._testMethodName).__func__.__unittest_expecting_failure__
            for case in cases_in(suite)
        }

    def test_a_listed_test_is_allowed_to_fail_and_an_unlisted_one_is_not(self):
        marked = self.runner_over((f"{Recorded.__module__}.Recorded.test_one",))

        self.assertEqual(marked[f"{Recorded.__module__}.Recorded.test_one"], True)
        self.assertEqual(marked[f"{Recorded.__module__}.Recorded.test_two"], False)

    def test_an_empty_list_marks_nothing(self):
        marked = self.runner_over(())

        self.assertEqual(set(marked.values()), {False})


class AnUnexpectedSuccessFailsTheRunTest(SimpleTestCase):

    def result_with(self, unexpected):
        return SimpleNamespace(failures=[], errors=[], unexpectedSuccesses=unexpected)

    def runner(self):
        return BehindThePoliciesRunner()

    def said(self, runner, result):
        spoken = io.StringIO()
        with redirect_stdout(spoken):
            outcome = runner.suite_result(TestSuite(), result)
        return outcome, spoken.getvalue()

    def test_a_clean_run_returns_no_failures_and_says_nothing(self):
        outcome, spoken = self.said(self.runner(), self.result_with([]))

        self.assertEqual(outcome, 0)
        self.assertEqual(spoken, "")

    def test_a_test_that_passed_while_listed_fails_the_run_and_says_so(self):
        outcome, spoken = self.said(self.runner(), self.result_with([Recorded("test_one")]))

        self.assertGreater(outcome, 0)
        self.assertIn("may only shrink", spoken)
        self.assertIn("Recorded.test_one", spoken)


class TheListNamesRealTestsTest(SimpleTestCase):

    def test_every_entry_is_a_dotted_path_of_at_least_three_parts(self):
        self.assertEqual([name for name in NOT_YET_BEHIND_THE_POLICIES if name.count(".") < 3], [])
