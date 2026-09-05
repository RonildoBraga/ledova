from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from offerings.models import Offering, OfferingStatus
from shared.tests.tenants import make_tenant

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
