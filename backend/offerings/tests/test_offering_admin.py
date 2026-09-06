from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from offerings.admin.offering import LOCKED_PAST_DRAFT
from offerings.models import Offering, OfferingExemption, OfferingStatus
from offerings.services.offering import CAP_ABOVE_HEADROOM
from shared.tests.tenants import make_tenant
from tokens.models import ShareIssuance
from tokens.models.choices import IssuanceStatus

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class OfferingAdminTest(TestCase):
    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        self.offering = self.tenant.offering
        self.operator = User.objects.create_superuser(email="operator@example.test", password="pw-12345678")
        self.client.force_login(self.operator)

    def _url(self, action):
        return reverse("admin:offerings_offering_transition", args=[self.offering.uuid, action])

    def _at(self, status):
        Offering.objects.filter(pk=self.offering.pk).update(status=status)
        self.offering.refresh_from_db()

    def _change_url(self):
        return reverse("admin:offerings_offering_change", args=[self.offering.pk])

    def _editable_fields(self):
        return set(self.client.get(self._change_url()).context["adminform"].form.fields)

    def _rewrite_the_economics(self):
        return self.client.post(
            self._change_url(),
            {
                "summary": "Edited by the operator",
                "use_of_proceeds": "",
                "documents": [],
                "settlement_assets": [],
                "token": self.tenant.token.pk,
                "exemption": OfferingExemption.MINIMUM_AMOUNT,
                "price_per_share": "0.01",
                "price_currency": "AUD",
                "minimum_shares": 1,
                "target_shares": 2,
                "cap_shares": 900,
                "maximum_shares": 800,
                "opens_at_0": "2030-01-01",
                "opens_at_1": "00:00:00",
                "closes_at_0": "2030-02-01",
                "closes_at_1": "00:00:00",
            },
        )

    def _economics(self):
        self.offering.refresh_from_db()
        return (
            self.offering.token_id,
            self.offering.exemption,
            str(self.offering.price_per_share),
            self.offering.minimum_shares,
            self.offering.target_shares,
            self.offering.cap_shares,
            self.offering.maximum_shares,
        )

    def test_the_add_form_is_closed(self):
        response = self.client.get(reverse("admin:offerings_offering_add"))
        self.assertEqual(response.status_code, 403)

    def test_start_review_needs_no_form(self):
        self._at(OfferingStatus.SUBMITTED)
        response = self.client.get(self._url("start-review"))
        self.assertEqual(response.status_code, 302)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.UNDER_REVIEW)
        self.assertEqual(self.offering.reviewed_by, self.operator)

    def test_approve_renders_then_records_the_notes(self):
        self._at(OfferingStatus.UNDER_REVIEW)
        self.assertEqual(self.client.get(self._url("approve")).status_code, 200)
        response = self.client.post(self._url("approve"), {"notes": "Documents checked"})
        self.assertEqual(response.status_code, 302)
        self.offering.refresh_from_db()
        self.assertEqual((self.offering.status, self.offering.review_notes), ("approved", "Documents checked"))

    def test_reject_requires_a_reason(self):
        self._at(OfferingStatus.SUBMITTED)
        self.assertEqual(self.client.post(self._url("reject"), {"reason": ""}).status_code, 200)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

        self.client.post(self._url("reject"), {"reason": "No prospectus"})
        self.offering.refresh_from_db()
        self.assertEqual((self.offering.status, self.offering.rejection_reason), ("rejected", "No prospectus"))

    def test_close_is_a_deliberate_act_and_never_automatic(self):
        self._at(OfferingStatus.APPROVED)
        self.client.post(self._url("close"), {"reason": "Fully subscribed"})
        self.offering.refresh_from_db()
        self.assertEqual((self.offering.status, self.offering.close_reason), ("closed", "Fully subscribed"))

    def test_an_illegal_transition_is_refused_and_reported(self):
        self._at(OfferingStatus.DRAFT)
        response = self.client.get(self._url("start-review"), follow=True)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.DRAFT)
        self.assertContains(response, "Cannot transition from")

    def test_the_change_page_shows_the_unissued_headroom(self):
        response = self.client.get(reverse("admin:offerings_offering_change", args=[self.offering.pk]))
        self.assertContains(response, "1000 authorized, 0 issued, 0 reserved by other live offerings")

    def test_the_economics_are_editable_in_draft_and_frozen_at_every_later_status(self):
        self._at(OfferingStatus.DRAFT)
        self.assertEqual(set(LOCKED_PAST_DRAFT) - self._editable_fields(), set())
        for status in OfferingStatus:
            if status == OfferingStatus.DRAFT:
                continue
            with self.subTest(status=status):
                self._at(status)
                self.assertEqual(set(LOCKED_PAST_DRAFT) & self._editable_fields(), set())

    def test_a_draft_offering_still_takes_a_rewrite_of_its_economics(self):
        self._at(OfferingStatus.DRAFT)
        before = self._economics()

        self.assertEqual(self._rewrite_the_economics().status_code, 302)

        self.assertNotEqual(self._economics(), before)
        self.assertEqual(self._economics()[0], self.tenant.token.pk)
        self.assertEqual(self.offering.cap_shares, 900)

    def test_a_submitted_offering_keeps_its_share_class_and_its_cap_through_the_change_form(self):
        self._at(OfferingStatus.SUBMITTED)
        before = self._economics()

        self.assertEqual(self._rewrite_the_economics().status_code, 302)

        self.assertEqual(self._economics(), before)
        self.assertEqual(self.offering.token_id, self.tenant.deployed_token.pk)
        self.assertEqual((self.offering.cap_shares, self.offering.summary), (100, "Edited by the operator"))

    def test_an_approved_offering_keeps_its_share_class_and_its_cap_through_the_change_form(self):
        self._at(OfferingStatus.APPROVED)
        before = self._economics()

        self.assertEqual(self._rewrite_the_economics().status_code, 302)

        self.assertEqual(self._economics(), before)

    def test_approval_is_refused_when_an_issuance_has_eaten_the_headroom_since_submit(self):
        self._at(OfferingStatus.SUBMITTED)
        ShareIssuance.objects.create(
            token=self.tenant.deployed_token,
            recipient_address="0x" + "1" * 40,
            amount="950",
            status=IssuanceStatus.COMPLETED,
        )

        response = self.client.post(self._url("approve"), {"notes": "Documents checked"}, follow=True)

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)
        self.assertContains(
            response,
            CAP_ABOVE_HEADROOM.format(
                cap=100,
                symbol=self.tenant.deployed_token.symbol,
                authorized=1000,
                issued=950,
                reserved=0,
                headroom=50,
            ),
        )
