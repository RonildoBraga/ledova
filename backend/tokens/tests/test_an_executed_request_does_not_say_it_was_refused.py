from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.test import TestCase

from shared.tests.tenants import make_tenant
from tokens.models import RequestStatus, ShareIssuanceRequest

_MIGRATION = import_module("tokens.migrations.0029_execution_notes")
MOVE = _MIGRATION.move_what_the_system_wrote
REVERSE = _MIGRATION.put_it_back_where_it_was

REVIEWER_WROTE = "Checked the shareholder agreement; the allocation matches clause 4."
NOT_WHITELISTED = "Recipient wallet is not whitelisted. Whitelist it before executing."


class AnExecutedRequestDoesNotSayItWasRefusedTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("issuer")
        self.request = ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address="0x" + "b" * 40,
            amount=10000,
            reason="Founder allocation",
            submitted_by=self.tenant.user,
            status=RequestStatus.SUBMITTED,
        )

    def _approved(self, notes=REVIEWER_WROTE):
        self.request.approve(self.tenant.user, notes=notes)
        self.request.refresh_from_db()
        return self.request

    def test_a_refusal_does_not_overwrite_what_the_reviewer_typed(self):
        self._approved()

        self.request.mark_refused(NOT_WHITELISTED)

        self.request.refresh_from_db()
        self.assertEqual(self.request.review_notes, REVIEWER_WROTE)
        self.assertIn(NOT_WHITELISTED, self.request.execution_notes)

    def test_a_failure_does_not_overwrite_it_either(self):
        self._approved()

        self.request.mark_failed("the node timed out")

        self.request.refresh_from_db()
        self.assertEqual(self.request.review_notes, REVIEWER_WROTE)
        self.assertIn("the node timed out", self.request.execution_notes)

    def test_a_refused_then_executed_request_reads_as_executed(self):
        self._approved()
        self.request.mark_refused(NOT_WHITELISTED)
        self.request.refresh_from_db()

        self.request.mark_executed()

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.EXECUTED)
        self.assertNotIn("Refused", self.request.review_notes)
        self.assertEqual(self.request.review_notes, REVIEWER_WROTE)

    def test_the_refusal_survives_as_history_rather_than_being_erased(self):
        self._approved()
        self.request.mark_refused(NOT_WHITELISTED)
        self.request.refresh_from_db()

        self.request.mark_executed()

        self.request.refresh_from_db()
        lines = self.request.execution_notes.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn(f"Refused: {NOT_WHITELISTED}", lines[0])
        self.assertIn("Executed", lines[1])

    def test_every_attempt_is_kept_in_the_order_it_happened(self):
        self._approved()
        self.request.mark_refused(NOT_WHITELISTED)
        self.request.refresh_from_db()
        self.request.mark_failed("the node timed out")
        self.request.refresh_from_db()
        self.request.status = RequestStatus.APPROVED
        self.request.save(update_fields=["status"])

        self.request.mark_executed()

        self.request.refresh_from_db()
        lines = self.request.execution_notes.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("Refused", lines[0])
        self.assertIn("Failed", lines[1])
        self.assertIn("Executed", lines[2])

    def test_each_line_carries_when_it_happened(self):
        self._approved()

        self.request.mark_refused(NOT_WHITELISTED)

        self.request.refresh_from_db()
        stamp = self.request.execution_notes.split(" ")[0]
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_a_request_nobody_reviewed_still_records_its_attempt(self):
        self.request.status = RequestStatus.APPROVED
        self.request.save(update_fields=["status"])

        self.request.mark_refused(NOT_WHITELISTED)

        self.request.refresh_from_db()
        self.assertEqual(self.request.review_notes, "")
        self.assertIn(NOT_WHITELISTED, self.request.execution_notes)


class TheMigrationMovesOnlyWhatTheSystemWroteTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("issuer")

    def a_request(self, review_notes):
        return ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address="0x" + "c" * 40,
            amount=10,
            reason="Allocation",
            submitted_by=self.tenant.user,
            status=RequestStatus.EXECUTED,
            review_notes=review_notes,
        )

    @staticmethod
    def run_the_move():
        return MOVE(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))

    @staticmethod
    def run_the_reverse():
        return REVERSE(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))

    def test_a_machine_refusal_moves_to_the_field_that_means_it(self):
        request = self.a_request(f"Execution refused: {NOT_WHITELISTED}")

        self.run_the_move()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, "")
        self.assertEqual(request.execution_notes, f"Execution refused: {NOT_WHITELISTED}")

    def test_a_machine_failure_moves_too(self):
        request = self.a_request("Execution failed: the node timed out")

        self.run_the_move()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, "")
        self.assertIn("the node timed out", request.execution_notes)

    def test_a_persons_note_is_left_exactly_where_it_is(self):
        request = self.a_request(REVIEWER_WROTE)

        self.run_the_move()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, REVIEWER_WROTE)
        self.assertEqual(request.execution_notes, "")

    def test_a_note_that_merely_mentions_a_refusal_is_a_persons_note(self):
        mentions = "The issuer says the earlier Execution refused: message was addressed."
        request = self.a_request(mentions)

        self.run_the_move()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, mentions)
        self.assertEqual(request.execution_notes, "")

    def test_the_reverse_puts_the_row_back_as_it_found_it(self):
        original = f"Execution refused: {NOT_WHITELISTED}"
        request = self.a_request(original)
        self.run_the_move()

        self.run_the_reverse()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, original)
        self.assertEqual(request.execution_notes, "")

    def test_the_reverse_leaves_a_log_this_migration_did_not_write(self):
        request = self.a_request("")
        request.mark_refused(NOT_WHITELISTED)
        request.refresh_from_db()
        written_by_the_new_code = request.execution_notes

        self.run_the_reverse()

        request.refresh_from_db()
        self.assertEqual(request.execution_notes, written_by_the_new_code)
        self.assertEqual(request.review_notes, "")
