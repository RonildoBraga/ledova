from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from shared.tests.tenants import make_tenant
from tokens.exceptions import InvalidTokenStateException, IssuanceRefusedException
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareToken
from tokens.services.capital_increase import submit_capital_increase
from tokens.services.share_token_service import ShareTokenService

CONSTRAINT_NAME = "one_capital_increase_in_flight_per_token"
GUARD = import_module("tokens.migrations.0026_one_capital_increase_in_flight").refuse_a_token_that_already_has_two


class ASecondRaiseIsRefusedWithAReasonTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("raise")
        self.token = self.tenant.deployed_token
        self.first = self.tenant.capital_increase
        CapitalIncreaseRequest.objects.filter(pk=self.first.pk).update(status=RequestStatus.SUBMITTED)
        self.first.refresh_from_db()

    def a_draft(self, additional=50):
        return CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=additional,
            new_authorized_total=int(self.token.total_supply) + additional,
            purpose="Second raise",
            board_resolution_reference="BOARD-2",
        )

    def test_the_second_submit_is_refused_before_the_constraint_sees_it(self):
        second = self.a_draft()

        with self.assertRaises(InvalidTokenStateException) as refusal:
            submit_capital_increase(second, self.tenant.user)

        self.assertIn("already has a capital increase in flight", str(refusal.exception.detail))
        second.refresh_from_db()
        self.assertEqual(second.status, RequestStatus.DRAFT)

    def test_the_refusal_names_the_one_that_is_in_flight(self):
        with self.assertRaises(InvalidTokenStateException) as refusal:
            submit_capital_increase(self.a_draft(), self.tenant.user)

        served = str(refusal.exception.detail)
        self.assertIn(self.token.symbol, served)
        self.assertIn(self.first.get_status_display(), served)

    def test_the_refusal_names_a_remedy_the_issuer_can_actually_reach(self):
        with self.assertRaises(InvalidTokenStateException) as refusal:
            submit_capital_increase(self.a_draft(), self.tenant.user)

        served = str(refusal.exception.detail)
        self.assertIn("ask the operator to reject it", served)
        self.assertNotIn("withdraw", served.lower())

    def test_a_draft_beside_one_in_flight_is_allowed_to_exist(self):
        self.a_draft()

        self.assertEqual(CapitalIncreaseRequest.objects.filter(token=self.token).count(), 2)

    def test_the_raise_is_allowed_once_the_first_one_finishes(self):
        CapitalIncreaseRequest.objects.filter(pk=self.first.pk).update(status=RequestStatus.EXECUTED)
        second = self.a_draft()

        submit_capital_increase(second, self.tenant.user)

        second.refresh_from_db()
        self.assertEqual(second.status, RequestStatus.SUBMITTED)

    def test_a_second_token_raises_on_its_own_schedule(self):
        other = make_tenant("raise-other")
        request = CapitalIncreaseRequest.objects.create(
            token=other.deployed_token,
            additional_shares=10,
            new_authorized_total=int(other.deployed_token.total_supply) + 10,
            purpose="Unrelated",
            board_resolution_reference="BOARD-3",
        )

        submit_capital_increase(request, other.user)

        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.SUBMITTED)


class TheDatabaseRefusesASecondInFlightRowTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("constraint")
        self.token = self.tenant.deployed_token
        CapitalIncreaseRequest.objects.filter(pk=self.tenant.capital_increase.pk).update(status=RequestStatus.SUBMITTED)

    def a_row(self, status):
        return CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=50,
            new_authorized_total=int(self.token.total_supply) + 50,
            purpose="Second raise",
            board_resolution_reference="BOARD-2",
            status=status,
        )

    def test_a_second_in_flight_row_cannot_be_written_at_all(self):
        for status in (
            RequestStatus.SUBMITTED,
            RequestStatus.UNDER_REVIEW,
            RequestStatus.APPROVED,
            RequestStatus.EXECUTING,
        ):
            with self.subTest(status=status), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self.a_row(status)

    def test_a_terminal_row_is_not_in_the_index(self):
        for status in (RequestStatus.DRAFT, RequestStatus.REJECTED, RequestStatus.EXECUTED, RequestStatus.FAILED):
            with self.subTest(status=status):
                row = self.a_row(status)
                self.assertEqual(CapitalIncreaseRequest.objects.get(pk=row.pk).status, status)


class ResumingAFailedRaiseWaitsForTheOneInFlightTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("resume")
        self.token = self.tenant.deployed_token
        CapitalIncreaseRequest.objects.all().delete()
        self.stalled = self.a_request(RequestStatus.FAILED, 100)
        self.waiting = self.a_request(RequestStatus.APPROVED, 50)
        self.service = ShareTokenService.__new__(ShareTokenService)

    def a_request(self, status, additional):
        return CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=additional,
            new_authorized_total=int(self.token.total_supply) + additional,
            purpose="Raise",
            board_resolution_reference=f"BOARD-{additional}",
            status=status,
        )

    def test_a_failed_raise_is_refused_with_a_reason_rather_than_an_integrity_error(self):
        with self.assertRaises(IssuanceRefusedException) as refusal:
            self.service._execute_capital_increase(self.stalled)

        self.stalled.refresh_from_db()
        self.assertIn("has another capital increase in flight", str(refusal.exception))
        self.assertIn(self.token.symbol, str(refusal.exception))
        self.assertEqual(self.stalled.status, RequestStatus.FAILED)

    def test_the_reason_survives_the_refusal_rather_than_rolling_back_with_it(self):
        with self.assertRaises(IssuanceRefusedException):
            self.service._execute_capital_increase(self.stalled)

        self.stalled.refresh_from_db()
        self.assertIn("has another capital increase in flight", self.stalled.execution_notes)
        self.assertEqual(self.stalled.review_notes, "")

    def test_the_one_in_flight_is_not_the_one_refused(self):
        with self.assertRaises(IssuanceRefusedException):
            self.service._execute_capital_increase(self.stalled)

        self.waiting.refresh_from_db()
        self.assertEqual((self.waiting.status, self.waiting.review_notes), (RequestStatus.APPROVED, ""))


class TheMigrationGuardRefusesRatherThanChoosingTest(TransactionTestCase):

    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.tenant = make_tenant("crowded")
        self.token = self.tenant.deployed_token
        CapitalIncreaseRequest.objects.all().delete()
        self.constraint = next(c for c in CapitalIncreaseRequest._meta.constraints if c.name == CONSTRAINT_NAME)
        with connection.schema_editor(atomic=False) as editor:
            editor.remove_constraint(CapitalIncreaseRequest, self.constraint)
        self.addCleanup(self.put_the_constraint_back)

    def put_the_constraint_back(self):
        CapitalIncreaseRequest.objects.all().delete()
        with connection.schema_editor(atomic=False) as editor:
            editor.add_constraint(CapitalIncreaseRequest, self.constraint)

    def a_request(self, status, additional=25):
        return CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=additional,
            new_authorized_total=int(self.token.total_supply) + additional,
            purpose="Raise",
            board_resolution_reference=f"BOARD-{additional}",
            status=status,
        )

    @staticmethod
    def run_the_guard():
        return GUARD(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))

    def test_one_in_flight_request_per_share_class_lets_the_migration_run(self):
        self.a_request(RequestStatus.SUBMITTED)
        self.a_request(RequestStatus.EXECUTED, additional=30)
        self.a_request(RequestStatus.DRAFT, additional=35)

        self.assertIsNone(self.run_the_guard())

    def test_two_in_flight_requests_stop_the_migration_and_name_both(self):
        first = self.a_request(RequestStatus.SUBMITTED)
        second = self.a_request(RequestStatus.APPROVED, additional=30)

        with self.assertRaises(RuntimeError) as refusal:
            self.run_the_guard()

        said = str(refusal.exception)
        self.assertIn(self.token.symbol, said)
        self.assertIn(str(self.token.uuid), said)
        self.assertIn(f"{first.uuid} (submitted)", said)
        self.assertIn(f"{second.uuid} (approved)", said)
        self.assertIn("a decision for an operator, not for a migration", said)

    def test_the_guard_changes_nothing_it_refuses_over(self):
        first = self.a_request(RequestStatus.SUBMITTED)
        second = self.a_request(RequestStatus.EXECUTING, additional=30)

        with self.assertRaises(RuntimeError):
            self.run_the_guard()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), (RequestStatus.SUBMITTED, RequestStatus.EXECUTING))
        self.assertEqual(CapitalIncreaseRequest.objects.filter(token=self.token).count(), 2)

    def test_a_terminal_pair_is_not_what_the_guard_is_looking_for(self):
        self.a_request(RequestStatus.REJECTED)
        self.a_request(RequestStatus.FAILED, additional=30)
        self.a_request(RequestStatus.EXECUTED, additional=35)

        self.assertIsNone(self.run_the_guard())

    def test_two_share_classes_with_one_each_are_not_a_crowd(self):
        other = ShareToken.objects.get(pk=self.tenant.deployed_token.pk)
        other.pk = None
        other.uuid = None
        other.symbol = "OTH"
        other.contract_address = "0x" + "7" * 40
        other.save()
        self.a_request(RequestStatus.SUBMITTED)
        CapitalIncreaseRequest.objects.create(
            token=other,
            additional_shares=40,
            new_authorized_total=int(other.total_supply) + 40,
            purpose="Raise",
            board_resolution_reference="BOARD-40",
            status=RequestStatus.SUBMITTED,
        )

        self.assertIsNone(self.run_the_guard())


class SubmissionReadsThePersistedDraftTest(TestCase):
    def test_a_stale_draft_cannot_submit_the_same_request_again(self):
        tenant = make_tenant("stale-submit")
        stale = CapitalIncreaseRequest.objects.get(pk=tenant.capital_increase.pk)
        submit_capital_increase(tenant.capital_increase, tenant.user)
        before = CapitalIncreaseRequest.objects.filter(pk=stale.pk).values().get()

        with self.assertRaises(InvalidTokenStateException):
            submit_capital_increase(stale, tenant.user)

        self.assertEqual(CapitalIncreaseRequest.objects.filter(pk=stale.pk).values().get(), before)

    def test_an_unrelated_database_failure_is_not_called_competition(self):
        tenant = make_tenant("submit-db-error")
        request = tenant.capital_increase
        before = CapitalIncreaseRequest.objects.filter(pk=request.pk).values().get()
        failure = DatabaseError("unrelated failure")

        with patch("tokens.services.capital_increase.dilution_for", side_effect=failure):
            with self.assertRaises(DatabaseError) as raised:
                submit_capital_increase(request, tenant.user)

        self.assertIs(raised.exception, failure)
        self.assertEqual(CapitalIncreaseRequest.objects.filter(pk=request.pk).values().get(), before)
