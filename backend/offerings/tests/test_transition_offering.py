from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from companies.models import Company, CompanyStatus
from offerings.exceptions import (
    InvalidOfferingTransitionException,
    OfferingRefusedException,
)
from offerings.models import Offering, OfferingStatus
from offerings.services import submit_offering, transition_offering
from offerings.services.offering import CAP_ABOVE_HEADROOM
from shared.tests.tenants import make_tenant
from tokens.models import ShareIssuance
from tokens.models.choices import IssuanceStatus

LEGAL = [
    (OfferingStatus.DRAFT, "submit", OfferingStatus.SUBMITTED),
    (OfferingStatus.SUBMITTED, "start_review", OfferingStatus.UNDER_REVIEW),
    (OfferingStatus.SUBMITTED, "approve", OfferingStatus.APPROVED),
    (OfferingStatus.UNDER_REVIEW, "approve", OfferingStatus.APPROVED),
    (OfferingStatus.SUBMITTED, "reject", OfferingStatus.REJECTED),
    (OfferingStatus.UNDER_REVIEW, "reject", OfferingStatus.REJECTED),
    (OfferingStatus.APPROVED, "close", OfferingStatus.CLOSED),
    (OfferingStatus.DRAFT, "withdraw", OfferingStatus.WITHDRAWN),
    (OfferingStatus.SUBMITTED, "withdraw", OfferingStatus.WITHDRAWN),
    (OfferingStatus.UNDER_REVIEW, "withdraw", OfferingStatus.WITHDRAWN),
]

METHOD_SOURCES = {
    "submit": {OfferingStatus.DRAFT},
    "start_review": {OfferingStatus.SUBMITTED},
    "approve": {OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW},
    "reject": {OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW},
    "close": {OfferingStatus.APPROVED},
    "withdraw": {OfferingStatus.DRAFT, OfferingStatus.SUBMITTED, OfferingStatus.UNDER_REVIEW},
}

NOTIFIED = {
    "submit": "Offering submitted",
    "start_review": "Offering review started",
    "approve": "Offering approved",
    "reject": "Offering rejected",
    "close": "Offering closed",
    "withdraw": "Offering withdrawn",
}


class TransitionOfferingTest(TestCase):
    def setUp(self):
        self.push = patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        self.offering = self.tenant.offering

    def _at(self, status):
        Offering.objects.filter(pk=self.offering.pk).update(status=status)
        self.offering.refresh_from_db()
        return self.offering

    def test_every_legal_transition_lands_on_its_target(self):
        for source, method, target in LEGAL:
            with self.subTest(source=source, method=method):
                transition_offering(self._at(source), method)
                self.offering.refresh_from_db()
                self.assertEqual(self.offering.status, target)

    def test_every_illegal_source_is_guarded(self):
        for method, sources in METHOD_SOURCES.items():
            for status in OfferingStatus:
                if status in sources:
                    continue
                with self.subTest(method=method, status=status):
                    with self.assertRaises(InvalidOfferingTransitionException):
                        transition_offering(self._at(status), method)
                    self.offering.refresh_from_db()
                    self.assertEqual(self.offering.status, status)

    def test_every_transition_notifies_the_owner_once(self):
        for source, method, _ in LEGAL:
            with self.subTest(method=method):
                self.push.reset_mock()
                transition_offering(self._at(source), method)
                self.assertEqual(self.push.defer.call_count, 1)
                kwargs = self.push.defer.call_args.kwargs
                self.assertEqual(kwargs["title"], NOTIFIED[method])
                self.assertEqual(kwargs["user_id"], str(self.tenant.user.pk))
                self.assertEqual(kwargs["data"]["offering_id"], str(self.offering.uuid))

    def test_a_rejection_reason_reaches_the_row_and_the_notification(self):
        transition_offering(self._at(OfferingStatus.SUBMITTED), "reject", reason="Prospectus missing")
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.rejection_reason, "Prospectus missing")
        self.assertIn("Prospectus missing", self.push.defer.call_args.kwargs["body"])

    def test_closing_records_when_and_why(self):
        transition_offering(self._at(OfferingStatus.APPROVED), "close", reason="Cap reached")
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.close_reason, "Cap reached")
        self.assertIsNotNone(self.offering.closed_at)

    def test_open_now_is_derived_and_needs_no_open_status(self):
        self.assertNotIn("open", [status.value for status in OfferingStatus])
        opened = timezone.now() - timedelta(days=2)
        just_closed = timezone.now() - timedelta(days=1)
        future = timezone.now() + timedelta(days=1)
        Offering.objects.filter(pk=self.offering.pk).update(
            status=OfferingStatus.APPROVED, opens_at=opened, closes_at=future
        )
        self.offering.refresh_from_db()
        self.assertTrue(self.offering.is_open)
        self.assertEqual(list(Offering.objects.open_now()), [self.offering])

        Offering.objects.filter(pk=self.offering.pk).update(closes_at=just_closed)
        self.offering.refresh_from_db()
        self.assertFalse(self.offering.is_open)
        self.assertEqual(list(Offering.objects.open_now()), [])

        Offering.objects.filter(pk=self.offering.pk).update(opens_at=future, closes_at=None)
        self.offering.refresh_from_db()
        self.assertFalse(self.offering.is_open)
        self.assertEqual(list(Offering.objects.open_now()), [])


class ApproveHeadroomTest(TestCase):
    def setUp(self):
        self.push = patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.tenant.company.refresh_from_db()
        self.token = self.tenant.deployed_token
        self.offering = self.tenant.offering
        self.offering.refresh_from_db()
        submit_offering(self.offering, submitted_by=self.tenant.user)
        self.push.reset_mock()

    def _issue(self, amount):
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address="0x" + "1" * 40,
            amount=amount,
            status=IssuanceStatus.COMPLETED,
        )

    def test_an_issuance_landing_after_submit_refuses_the_approval_and_names_the_shortfall(self):
        self._issue("950")

        with self.assertRaises(OfferingRefusedException) as raised:
            transition_offering(self.offering, "approve")

        self.assertEqual(
            str(raised.exception.detail),
            CAP_ABOVE_HEADROOM.format(
                cap=100, symbol=self.token.symbol, authorized=1000, issued=950, reserved=0, headroom=50
            ),
        )
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)
        self.push.defer.assert_not_called()

    def test_an_issuance_that_leaves_the_cap_covered_still_approves(self):
        self._issue("900")

        transition_offering(self.offering, "approve")

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.APPROVED)
        self.assertEqual(self.push.defer.call_args.kwargs["title"], "Offering approved")

    def test_a_pending_issuance_never_counts_against_the_headroom(self):
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address="0x" + "2" * 40,
            amount="950",
            status=IssuanceStatus.PENDING,
        )

        transition_offering(self.offering, "approve")

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.APPROVED)

    def test_rejecting_and_closing_never_ask_about_the_headroom(self):
        self._issue("1000")

        transition_offering(self.offering, "reject", reason="Out of headroom")

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.REJECTED)
