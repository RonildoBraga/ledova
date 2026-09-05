import importlib
import os
import re
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import clear_url_caches, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from operators.models import Operator
from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
)
from users.models.investor_classification import DECLARATION_TEXT
from users.tests.factories import (
    attach_evidence,
    make_classification,
    make_investor,
    verified_classification,
)

User = get_user_model()
BASE = "/api/investor-classifications/"
EVIDENCE_BYTES = b"%PDF-1.4 net asset evidence"
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _pdf(name="certificate.pdf"):
    return SimpleUploadedFile(name, EVIDENCE_BYTES, content_type="application/pdf")


class InvestorClassificationApiTest(APITestCase):

    def setUp(self):
        self.user, self.account = make_investor("api-owner")
        self.other_user, self.other_account = make_investor("api-other")
        self.client.force_authenticate(self.user)

    def _payload(self, **overrides):
        payload = {
            "user_account": str(self.account.uuid),
            "category": InvestorCategory.PROFESSIONAL_INVESTOR.value,
            "declaration_accepted": "true",
            "declared_basis": "I run a licensed fund",
            "evidence_file": _pdf(),
        }
        payload.update(overrides)
        return payload

    def test_a_submission_freezes_the_declaration_and_captures_the_upload(self):
        response = self.client.post(BASE, self._payload(), format="multipart")

        self.assertEqual(response.status_code, 201, response.content)
        classification = InvestorClassification.objects.get(uuid=response.json()["uuid"])
        self.assertEqual(classification.status, InvestorClassificationStatus.SUBMITTED)
        self.assertEqual(classification.declaration_text, DECLARATION_TEXT[InvestorCategory.PROFESSIONAL_INVESTOR])
        self.assertEqual(classification.evidence_file_size, len(EVIDENCE_BYTES))
        self.assertEqual(classification.evidence_mime_type, "application/pdf")
        self.assertIsNotNone(classification.submitted_at)

    def test_the_evidence_url_is_the_authenticated_route_not_media(self):
        response = self.client.post(BASE, self._payload(), format="multipart")

        url = response.json()["evidenceUrl"]
        self.assertIn(f"{BASE}{response.json()['uuid']}/evidence/", url)
        self.assertNotIn("/media/", url)

    def test_a_declaration_that_is_not_accepted_is_refused(self):
        response = self.client.post(BASE, self._payload(declaration_accepted="false"), format="multipart")

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_oversized_upload_is_refused(self):
        big = SimpleUploadedFile("big.pdf", b"0" * (10 * 1024 * 1024 + 1), content_type="application/pdf")

        response = self.client.post(BASE, self._payload(evidence_file=big), format="multipart")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("10 MB", str(response.json()))

    def test_a_disallowed_mime_type_is_refused(self):
        bad = SimpleUploadedFile("evidence.txt", b"plain", content_type="text/plain")

        response = self.client.post(BASE, self._payload(evidence_file=bad), format="multipart")

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_second_open_submission_is_refused_with_400_not_a_database_error(self):
        make_classification(self.account)

        response = self.client.post(BASE, self._payload(), format="multipart")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("awaiting review", str(response.json()))

    def test_another_tenants_account_cannot_be_named(self):
        response = self.client.post(BASE, self._payload(user_account=str(self.other_account.uuid)), format="multipart")

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_associated_person_claim_must_name_an_active_issuer(self):
        owner = User.objects.create_user(email="assoc-owner@example.test", password="pw-12345678")
        company = Company.objects.create(
            owner=owner,
            name="Assoc Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="555666777",
            status=CompanyStatus.ACTIVE,
        )

        refused = self.client.post(
            BASE, self._payload(category=InvestorCategory.ASSOCIATED_PERSON.value), format="multipart"
        )
        accepted = self.client.post(
            BASE,
            self._payload(category=InvestorCategory.ASSOCIATED_PERSON.value, company=str(company.uuid)),
            format="multipart",
        )

        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(accepted.status_code, 201, accepted.content)

    def test_a_company_may_not_be_named_on_an_unscoped_category(self):
        owner = User.objects.create_user(email="scope-owner@example.test", password="pw-12345678")
        company = Company.objects.create(
            owner=owner,
            name="Scope Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="444555666",
            status=CompanyStatus.ACTIVE,
        )

        response = self.client.post(BASE, self._payload(company=str(company.uuid)), format="multipart")

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_accountant_certificate_needs_its_certifier_fields(self):
        response = self.client.post(
            BASE, self._payload(category=InvestorCategory.ACCOUNTANT_CERTIFICATE.value), format="multipart"
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("certifierName", response.json())

    def test_a_certificate_older_than_two_years_is_refused(self):
        stale = (timezone.now() - timedelta(days=800)).date()

        response = self.client.post(
            BASE,
            self._payload(
                category=InvestorCategory.ACCOUNTANT_CERTIFICATE.value,
                certificate_issued_at=stale.isoformat(),
                certifier_name="A Certifier",
                certifier_body="ca_anz",
                certifier_membership_number="12345",
            ),
            format="multipart",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("certificateIssuedAt", response.json())

    def test_a_fresh_certificate_is_accepted(self):
        fresh = (timezone.now() - timedelta(days=30)).date()

        response = self.client.post(
            BASE,
            self._payload(
                category=InvestorCategory.ACCOUNTANT_CERTIFICATE.value,
                certificate_issued_at=fresh.isoformat(),
                certifier_name="A Certifier",
                certifier_body="cpa_australia",
                certifier_membership_number="12345",
            ),
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.content)

    def test_the_list_shows_only_the_callers_own_claims(self):
        mine = make_classification(self.account)
        make_classification(self.other_account)

        response = self.client.get(BASE)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(mine.uuid)])

    def test_a_submitted_claim_can_be_deleted_but_a_verified_one_cannot(self):
        reviewer = User.objects.create_user(email="del-reviewer@example.test", password="pw-12345678")
        submitted = make_classification(self.account)

        self.assertEqual(self.client.delete(f"{BASE}{submitted.uuid}/").status_code, 204)

        verified = verified_classification(self.account, reviewer)
        self.assertEqual(self.client.delete(f"{BASE}{verified.uuid}/").status_code, 404)
        self.assertTrue(InvestorClassification.objects.filter(uuid=verified.uuid).exists())

    def test_the_submission_is_immutable(self):
        classification = make_classification(self.account)

        self.assertEqual(self.client.patch(f"{BASE}{classification.uuid}/", {}).status_code, 405)
        self.assertEqual(self.client.put(f"{BASE}{classification.uuid}/", {}).status_code, 405)


class EligibilityEndpointTest(APITestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="ep-reviewer@example.test", password="pw-12345678")
        self.user, self.account = make_investor("eligibility-endpoint")
        operator = Operator.get()
        operator.investor_kyc_required = True
        operator.save(update_fields=["investor_kyc_required"])

    def test_it_reports_the_callers_own_state(self):
        self.client.force_authenticate(self.user)

        refused = self.client.get(f"{BASE}eligibility/")
        self.assertEqual(refused.status_code, 200, refused.content)
        self.assertFalse(refused.json()["isEligible"])
        self.assertEqual(refused.json()["reasons"], ["no_live_classification"])
        self.assertEqual(refused.json()["account"], str(self.account.uuid))
        self.assertIsNone(refused.json()["classification"])

        classification = verified_classification(self.account, self.reviewer)
        allowed = self.client.get(f"{BASE}eligibility/")
        self.assertTrue(allowed.json()["isEligible"])
        self.assertEqual(allowed.json()["classification"]["uuid"], str(classification.uuid))

    def test_it_refuses_an_anonymous_caller(self):
        self.assertEqual(self.client.get(f"{BASE}eligibility/").status_code, 401)


class EvidenceViewTest(APITestCase):

    def setUp(self):
        self.user, self.account = make_investor("evidence-owner")
        self.other_user, self.other_account = make_investor("evidence-other")
        self.staff = User.objects.create_superuser(email="evidence-staff@example.test", password="pw-12345678")
        self.classification = attach_evidence(make_classification(self.account), EVIDENCE_BYTES)
        self.url = f"{BASE}{self.classification.uuid}/evidence/"

    @staticmethod
    def _streamed(response):
        return b"".join(response.streaming_content)

    def test_the_owner_reads_the_bytes_through_the_api(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(self._streamed(response), EVIDENCE_BYTES)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_it_streams_rather_than_redirecting_to_media(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertNotIn(response.status_code, (301, 302, 303, 307, 308))
        self.assertIsNone(response.headers.get("Location"))
        self.assertNotIn("/media/", response.headers.get("Content-Disposition", ""))

    def test_another_tenant_gets_404(self):
        self.client.force_authenticate(self.other_user)

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_an_anonymous_caller_gets_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_staff_read_the_same_bytes_through_the_admin(self):
        self.client.force_authenticate(None)
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("admin:users_investorclassification_evidence", args=[self.classification.uuid])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._streamed(response), EVIDENCE_BYTES)

    def test_the_admin_evidence_view_refuses_a_non_staff_caller(self):
        self.client.force_authenticate(None)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("admin:users_investorclassification_evidence", args=[self.classification.uuid])
        )

        self.assertIn(response.status_code, (302, 403))

    def test_a_claim_with_no_evidence_is_404(self):
        bare = make_classification(self.other_account)
        self.client.force_authenticate(self.other_user)

        self.assertEqual(self.client.get(f"{BASE}{bare.uuid}/evidence/").status_code, 404)


@override_settings(STORAGES=ADMIN_STORAGES)
class AdminTransitionViewTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(email="admin-transitions@example.test", password="pw-12345678")
        self.client.force_login(self.staff)
        _, self.account = make_investor("admin-transitions")
        self.classification = make_classification(self.account, certificate_issued_at=date(2026, 1, 1))

    def _url(self, action):
        return reverse("admin:users_investorclassification_transition", args=[self.classification.uuid, action])

    def test_the_verify_form_renders_with_the_default_expiry(self):
        response = self.client.get(self._url("verify"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verify Classification")

    def test_verifying_through_the_admin_goes_through_the_service(self):
        expires_at = timezone.now() + timedelta(days=400)

        response = self.client.post(
            self._url("verify"),
            {"expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"), "notes": "Checked"},
        )

        self.assertEqual(response.status_code, 302)
        self.classification.refresh_from_db()
        self.assertEqual(self.classification.status, InvestorClassificationStatus.VERIFIED)
        self.assertEqual(self.classification.reviewed_by, self.staff)

    def test_rejecting_through_the_admin_records_the_reason(self):
        response = self.client.post(self._url("reject"), {"reason": "No evidence"})

        self.assertEqual(response.status_code, 302)
        self.classification.refresh_from_db()
        self.assertEqual(self.classification.status, InvestorClassificationStatus.REJECTED)
        self.assertEqual(self.classification.rejection_reason, "No evidence")

    def test_an_illegal_transition_reports_the_guard_rather_than_changing_the_row(self):
        response = self.client.post(self._url("revoke"), {"reason": "Too soon"}, follow=True)

        self.classification.refresh_from_db()
        self.assertEqual(self.classification.status, InvestorClassificationStatus.SUBMITTED)
        self.assertContains(response, "Cannot transition from")

    def test_an_anonymous_caller_is_sent_to_the_admin_login(self):
        self.client.logout()

        response = self.client.get(self._url("verify"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])


@override_settings(STORAGES=ADMIN_STORAGES)
class EvidenceIsNotServedFromMediaTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(email="media-staff@example.test", password="pw-12345678")
        _, account = make_investor("media-leak")
        self.classification = attach_evidence(make_classification(account), EVIDENCE_BYTES)

    @staticmethod
    def _reloaded_urlconf():
        import ledova_backend.urls

        importlib.reload(ledova_backend.urls)
        clear_url_caches()

    def test_the_admin_change_page_prints_no_media_href(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:users_investorclassification_change", args=[self.classification.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(re.findall(r'href="(/media/[^"]*)"', response.content.decode()), [])

    def test_the_evidence_file_has_no_public_url_at_all(self):
        with self.assertRaises(ValueError):
            self.classification.evidence_file.url

    def test_an_anonymous_caller_cannot_fetch_the_evidence_from_media_under_debug(self):
        media_path = f"{settings.MEDIA_URL}{self.classification.evidence_file.name}"

        with override_settings(DEBUG=True, ALLOWED_HOSTS=["*"]):
            self._reloaded_urlconf()
            try:
                response = Client().get(media_path)
            finally:
                self._reloaded_urlconf()

        self.assertEqual(response.status_code, 404)

    def test_the_evidence_bytes_live_outside_the_served_media_root(self):
        path = self.classification.evidence_file.path

        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.startswith(os.path.abspath(settings.PRIVATE_MEDIA_ROOT)))
        self.assertFalse(path.startswith(os.path.abspath(settings.MEDIA_ROOT)))
