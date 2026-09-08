from importlib import import_module
from types import SimpleNamespace
from unittest import skipUnless

from django.apps import apps
from django.conf import settings
from django.test import TestCase, TransactionTestCase

from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareIssuanceRequest

_MIGRATION = import_module("tokens.migrations.0029_execution_notes")
ANNOTATE = _MIGRATION.retain_legacy_history
REVERSE = _MIGRATION.remove_legacy_context

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

    def test_a_later_attempt_keeps_history_written_since_the_request_was_loaded(self):
        self._approved()
        stale_request = ShareIssuanceRequest.objects.get(pk=self.request.pk)
        self.request.mark_refused(NOT_WHITELISTED)

        stale_request.mark_executed()

        self.request.refresh_from_db()
        self.assertEqual(self.request.review_notes, REVIEWER_WROTE)
        self.assertEqual(len(self.request.execution_notes.splitlines()), 2)
        self.assertIn(NOT_WHITELISTED, self.request.execution_notes)
        self.assertTrue(self.request.execution_notes.endswith("Executed"))

    def test_a_request_nobody_reviewed_still_records_its_attempt(self):
        self.request.status = RequestStatus.APPROVED
        self.request.save(update_fields=["status"])

        self.request.mark_refused(NOT_WHITELISTED)

        self.request.refresh_from_db()
        self.assertEqual(self.request.review_notes, "")
        self.assertIn(NOT_WHITELISTED, self.request.execution_notes)


class TheMigrationPreservesUnattributedNotesTest(TestCase):

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
    def run_the_annotation():
        return ANNOTATE(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))

    @staticmethod
    def run_the_reverse():
        return REVERSE(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))

    def test_an_old_refusal_is_preserved_with_context_that_identifies_it_as_history(self):
        request = self.a_request(f"Execution refused: {NOT_WHITELISTED}")

        self.run_the_annotation()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, f"Execution refused: {NOT_WHITELISTED}")
        self.assertEqual(request.execution_notes, _MIGRATION.LEGACY_CONTEXT)

    def test_an_old_failure_is_preserved_without_guessing_who_wrote_it(self):
        request = self.a_request("Execution failed: the node timed out")

        self.run_the_annotation()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, "Execution failed: the node timed out")
        self.assertEqual(request.execution_notes, _MIGRATION.LEGACY_CONTEXT)

    def test_a_persons_note_is_left_exactly_where_it_is(self):
        request = self.a_request(REVIEWER_WROTE)

        self.run_the_annotation()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, REVIEWER_WROTE)
        self.assertEqual(request.execution_notes, _MIGRATION.LEGACY_CONTEXT)

    def test_a_reviewers_approval_can_begin_with_either_execution_prefix(self):
        for prefix in ("Execution refused: ", "Execution failed: "):
            with self.subTest(prefix=prefix):
                notes = f"{prefix}during the earlier proposal; this allocation is now approved."
                request = self.a_request("")
                request.status = RequestStatus.SUBMITTED
                request.save(update_fields=["status"])
                request.approve(self.tenant.user, notes=notes)

                self.run_the_annotation()

                request.refresh_from_db()
                self.assertEqual(request.review_notes, notes)

    def test_a_note_that_merely_mentions_a_refusal_is_a_persons_note(self):
        mentions = "The issuer says the earlier Execution refused: message was addressed."
        request = self.a_request(mentions)

        self.run_the_annotation()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, mentions)
        self.assertEqual(request.execution_notes, _MIGRATION.LEGACY_CONTEXT)

    def test_the_reverse_puts_the_row_back_as_it_found_it(self):
        original = f"Execution refused: {NOT_WHITELISTED}"
        request = self.a_request(original)
        self.run_the_annotation()

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

    def test_running_the_annotation_or_reverse_again_keeps_new_execution_history(self):
        request = self.a_request(REVIEWER_WROTE)
        self.run_the_annotation()
        request.refresh_from_db()
        request.mark_executed()
        history = request.execution_notes

        self.run_the_annotation()
        self.run_the_reverse()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, REVIEWER_WROTE)
        self.assertEqual(request.execution_notes, history)

    def test_an_empty_review_note_does_not_acquire_invented_history(self):
        request = self.a_request("")

        self.run_the_annotation()

        request.refresh_from_db()
        self.assertEqual(request.review_notes, "")
        self.assertEqual(request.execution_notes, "")


_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Requires actual token migrations")
class ExecutionNotesMigrationRoundTripTest(TransactionTestCase):

    def test_both_request_tables_preserve_review_and_machine_notes_through_a_round_trip(self):
        self.addCleanup(restore_every_migration)
        tenant = make_tenant("issuer")
        cases = []
        for model, fields in (
            (ShareIssuanceRequest, {"recipient_address": "0x" + "c" * 40, "amount": 10, "reason": "Allocation"}),
            (
                CapitalIncreaseRequest,
                {
                    "additional_shares": 10,
                    "new_authorized_total": 1010,
                    "purpose": "Growth",
                    "board_resolution_reference": "Board 1",
                },
            ),
        ):
            for notes in (
                REVIEWER_WROTE,
                f"Execution refused: {NOT_WHITELISTED}",
                "Execution failed: the node timed out",
            ):
                request = model.objects.create(
                    token=tenant.deployed_token,
                    submitted_by=tenant.user,
                    status=RequestStatus.EXECUTED,
                    review_notes=notes,
                    **fields,
                )
                cases.append((model.__name__, request.pk, notes))

        before = [("tokens", "0030_superseded_capital_increase")]
        after = [("tokens", "0029_execution_notes")]
        migrate_to(before)
        migrated = migrate_to(after)
        for name, pk, notes in cases:
            request = migrated.get_model("tokens", name).objects.get(pk=pk)
            self.assertEqual(request.review_notes, notes)
            self.assertEqual(request.execution_notes, _MIGRATION.LEGACY_CONTEXT)

        reversed_apps = migrate_to(before)
        for name, pk, notes in cases:
            self.assertEqual(reversed_apps.get_model("tokens", name).objects.get(pk=pk).review_notes, notes)
