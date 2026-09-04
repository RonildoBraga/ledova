"""End-to-end coverage of the company application lifecycle over the REST API and the admin actions."""

from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from companies.admin.company import CompanyAdmin
from companies.exceptions import InvalidStatusTransitionException
from companies.models import (
    LISTING_REQUIRED_DOCUMENTS,
    Company,
    CompanyDocument,
    CompanyStatus,
)
from users.models import UserProfile

User = get_user_model()


class ApplicationLifecycleTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        self.other = User.objects.create_user(email="other@example.test", password="pw-12345678")
        self.staff = User.objects.create_user(email="staff@example.test", password="pw-12345678", is_staff=True)
        self.company = Company.objects.create(owner=self.owner, name="Draft Pty Ltd", acn="123456789")
        self.url = f"/api/v1/companies/{self.company.uuid}/"

    def upload_required_documents(self, company=None):
        company = company or self.company
        for doc_type in LISTING_REQUIRED_DOCUMENTS:
            CompanyDocument.objects.create(
                company=company,
                document_type=doc_type,
                name=doc_type.label,
                external_url="https://files.example.test/doc",
                file_size=10,
                mime_type="application/pdf",
            )

    def set_status(self, new_status, reason="", expect=200):
        self.client.force_authenticate(self.staff)
        response = self.client.post(f"{self.url}status/", {"status": new_status, "reason": reason}, format="json")
        self.assertEqual(response.status_code, expect, response.data)
        self.company.refresh_from_db()
        return response

    def test_register_creates_draft_company_and_primary_contact_profile(self):
        UserProfile.objects.create(
            user=self.other, full_name="Old Name", phone_country_code="+61", phone_number="0400000000"
        )
        self.client.force_authenticate(self.other)
        payload = {
            "name": "New Co Pty Ltd",
            "acn": "987 654 321",
            "companyType": "pty",
            # Clients send "<country_code> <number>" composed from the profile step.
            "primaryContact": {"firstName": "Ada", "lastName": "Lovelace", "phone": "+61 0400000000"},
        }
        response = self.client.post("/api/v1/companies/", payload, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("message", response.data)
        company = Company.objects.get(acn="987654321")
        self.assertEqual(response.data["company"]["uuid"], str(company.uuid))
        self.assertEqual(company.status, CompanyStatus.DRAFT)
        self.assertEqual(company.owner, self.other)
        profile = UserProfile.objects.get(user=self.other)
        self.assertEqual(profile.full_name, "Ada Lovelace")
        self.assertEqual(profile.phone_country_code, "+61")
        self.assertEqual(profile.phone_number, "0400000000")

    def test_register_rejects_duplicate_acn(self):
        self.client.force_authenticate(self.other)
        payload = {"name": "Dup", "acn": self.company.acn, "primaryContact": {"firstName": "A", "lastName": "B"}}
        response = self.client.post("/api/v1/companies/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("acn", response.data)
        self.assertEqual(Company.objects.filter(acn=self.company.acn).count(), 1)

    def test_submit_requires_confirmation(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"{self.url}submit/", {"confirm": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm", response.data)

    def test_submit_lists_missing_required_documents(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"{self.url}submit/", {"confirm": True}, format="json")

        self.assertEqual(response.status_code, 400)
        detail = str(response.data["detail"])
        self.assertIn("Missing required documents", detail)
        for doc_type in LISTING_REQUIRED_DOCUMENTS:
            self.assertIn(doc_type.label, detail)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.DRAFT)

    def test_submit_succeeds_once_required_documents_are_uploaded(self):
        self.upload_required_documents()
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"{self.url}submit/", {"confirm": True}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["company"]["status"], "submitted")
        self.assertTrue(response.data["company"]["is_pending_review"])
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.SUBMITTED)
        self.assertEqual(self.company.submitted_by, self.owner)
        self.assertIsNotNone(self.company.submitted_at)

        second = self.client.post(f"{self.url}submit/", {"confirm": True}, format="json")
        self.assertEqual(second.status_code, 400)
        self.assertIn("Cannot transition from 'Submitted for Review' to 'Submitted for Review'", str(second.data))

    def test_staff_walks_the_full_lifecycle_and_owner_resubmits(self):
        self.upload_required_documents()
        self.company.submit(submitted_by=self.owner)

        self.set_status("review")
        self.assertEqual(self.company.status, CompanyStatus.REVIEW)
        self.assertIsNotNone(self.company.review_started_at)

        self.set_status("info_required", reason="Need the latest share register")
        self.assertEqual(self.company.status, CompanyStatus.INFO_REQUIRED)
        self.assertEqual(self.company.info_request_reason, "Need the latest share register")

        self.client.force_authenticate(self.owner)
        response = self.client.post(f"{self.url}resubmit/", {"response": "Uploaded it"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["company"]["status"], "submitted")
        self.company.refresh_from_db()
        self.assertEqual(self.company.info_request_reason, "")

        self.set_status("review")
        response = self.set_status("approved")
        self.assertEqual(response.data["message"], "Company status updated to Approved")
        self.assertEqual(self.company.approved_by, self.staff)

        self.set_status("active")
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)
        self.assertIsNotNone(self.company.activated_at)

        self.set_status("warning", reason="Late filing")
        self.assertEqual(self.company.warning_reason, "Late filing")
        self.set_status("active")
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

        self.set_status("suspended", reason="Investigation")
        self.assertEqual(self.company.suspension_reason, "Investigation")
        self.set_status("active")
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

        self.set_status("delisted", reason="Wound up")
        self.assertEqual(self.company.status, CompanyStatus.DELISTED)
        self.assertEqual(self.company.delisting_reason, "Wound up")

    def test_status_update_rejects_invalid_transitions(self):
        response = self.set_status("approved", expect=400)
        self.assertEqual(str(response.data["detail"]), "Cannot transition from 'Draft' to 'Approved'.")
        self.assertEqual(self.company.status, CompanyStatus.DRAFT)

        response = self.set_status("active", expect=400)
        self.assertEqual(str(response.data["detail"]), "Cannot transition from 'Draft' to 'Active'.")

        response = self.set_status("submitted", expect=400)
        self.assertEqual(str(response.data["detail"]), "Cannot transition from 'Draft' to 'Submitted for Review'.")

        response = self.set_status("delisted", reason="never listed", expect=400)
        self.assertEqual(str(response.data["detail"]), "Cannot transition from 'Draft' to 'Delisted'.")

        response = self.set_status("bogus", expect=400)
        self.assertIn("status", response.data)

    def test_rejection_requires_a_reason(self):
        self.company.status = CompanyStatus.SUBMITTED
        self.company.save(update_fields=["status"])

        response = self.set_status("rejected", expect=400)
        self.assertIn("reason", response.data)
        self.assertEqual(self.company.status, CompanyStatus.SUBMITTED)

        self.set_status("rejected", reason="Incomplete constitution")
        self.assertEqual(self.company.status, CompanyStatus.REJECTED)
        self.assertEqual(self.company.rejection_reason, "Incomplete constitution")
        self.assertEqual(self.company.rejected_by, self.staff)

    def test_withdraw_with_and_without_reason(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"{self.url}withdraw/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.WITHDRAWN)
        self.assertEqual(self.company.withdrawal_reason, "")

        submitted = Company.objects.create(owner=self.owner, name="Second", acn="222222222", status="submitted")
        response = self.client.post(
            f"/api/v1/companies/{submitted.uuid}/withdraw/", {"reason": "Changed plans"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        submitted.refresh_from_db()
        self.assertEqual(submitted.status, CompanyStatus.WITHDRAWN)
        self.assertEqual(submitted.withdrawal_reason, "Changed plans")

    def test_withdraw_and_resubmit_reject_wrong_states(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"{self.url}resubmit/", {"response": "n/a"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), "Cannot transition from 'Draft' to 'Submitted for Review'.")

        self.company.status = CompanyStatus.ACTIVE
        self.company.save(update_fields=["status"])
        response = self.client.post(f"{self.url}withdraw/", {"reason": "too late"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), "Cannot transition from 'Active' to 'Withdrawn'.")
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)

    def test_non_staff_cannot_reach_administrative_routes(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f"{self.url}status/", {"status": "review"}, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"{self.url}api-key/").status_code, 403)
        self.assertEqual(self.client.post(f"{self.url}api-key/").status_code, 403)

        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"{self.url}status/", {"status": "review"}, format="json").status_code, 401)
        self.assertEqual(self.client.get(f"{self.url}api-key/").status_code, 401)

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f"{self.url}submit/", {"confirm": True}, format="json").status_code, 404)
        self.assertEqual(self.client.post(f"{self.url}withdraw/", {}, format="json").status_code, 404)

    def test_model_transitions_raise_api_exceptions_for_admin_and_api_alike(self):
        with self.assertRaises(InvalidStatusTransitionException) as ctx:
            self.company.approve(approved_by=self.staff)
        self.assertEqual(str(ctx.exception.detail), "Cannot transition from 'Draft' to 'Approved'.")
        self.assertEqual(ctx.exception.status_code, 400)

        for transition in (
            self.company.start_review,
            self.company.resubmit,
            self.company.activate,
            self.company.resolve_warning,
            self.company.reinstate,
            lambda: self.company.request_info("x"),
            lambda: self.company.reject("x"),
            lambda: self.company.issue_warning("x"),
            lambda: self.company.suspend("x"),
            lambda: self.company.delist("x"),
        ):
            with self.assertRaises(InvalidStatusTransitionException):
                transition()
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.DRAFT)

    def test_admin_bulk_actions_call_the_model_transitions(self):
        self.company.status = CompanyStatus.REVIEW
        self.company.save(update_fields=["status"])
        draft = Company.objects.create(owner=self.owner, name="Still draft", acn="333333333")
        admin = CompanyAdmin(Company, AdminSite())
        admin.message_user = lambda *args, **kwargs: None
        request = SimpleNamespace(user=self.staff)

        admin.approve_action(request, Company.objects.all())
        self.company.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.APPROVED)
        self.assertEqual(self.company.approved_by, self.staff)
        self.assertEqual(draft.status, CompanyStatus.DRAFT)

        admin.activate_action(request, Company.objects.all())
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.ACTIVE)
