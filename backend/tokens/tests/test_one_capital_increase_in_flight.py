from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase

from shared.tests.tenants import make_tenant
from tokens.exceptions import InvalidTokenStateException
from tokens.models import CapitalIncreaseRequest, RequestStatus
from tokens.services.capital_increase import submit_capital_increase


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
