"""Every company application event reaches the owner once: one Notification row, one deferred push job."""

from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from procrastinate.contrib.django.models import ProcrastinateJob
from rest_framework.test import APITestCase

from companies.admin.company import CompanyAdmin
from companies.models import (
    LISTING_REQUIRED_DOCUMENTS,
    Company,
    CompanyDocument,
    CompanyStatus,
)
from companies.services import APPLICANT_NOTIFICATIONS, transition_company
from users.models import Notification
from users.tasks.notifications import send_push_notification as run_task

User = get_user_model()
TASK = "companies.services.company.send_push_notification"
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# (transition, status it runs from, kwargs, expected title, expected body)
MATRIX = [
    ("submit", CompanyStatus.DRAFT, {}, "Application submitted", "Acme Pty Ltd was submitted for review."),
    ("start_review", CompanyStatus.SUBMITTED, {}, "Review started", "The review of Acme Pty Ltd has started."),
    (
        "request_info",
        CompanyStatus.REVIEW,
        {"reason": "Latest share register"},
        "More information requested",
        "More information requested: Latest share register",
    ),
    (
        "resubmit",
        CompanyStatus.INFO_REQUIRED,
        {"response": "Uploaded"},
        "Application resubmitted",
        "Acme Pty Ltd was resubmitted with your response.",
    ),
    ("approve", CompanyStatus.REVIEW, {}, "Application approved", "Acme Pty Ltd has been approved."),
    (
        "reject",
        CompanyStatus.REVIEW,
        {"reason": "Constitution missing"},
        "Application rejected",
        "Acme Pty Ltd was rejected: Constitution missing",
    ),
    ("activate", CompanyStatus.APPROVED, {}, "Company activated", "Acme Pty Ltd is now active."),
    (
        "withdraw",
        CompanyStatus.SUBMITTED,
        {"reason": "Changed plans"},
        "Application withdrawn",
        "Acme Pty Ltd was withdrawn.",
    ),
]
SILENT = [
    ("issue_warning", CompanyStatus.ACTIVE, {"reason": "Late filing"}),
    ("resolve_warning", CompanyStatus.WARNING, {}),
    ("suspend", CompanyStatus.ACTIVE, {"reason": "Investigation"}),
    ("reinstate", CompanyStatus.SUSPENDED, {}),
    ("delist", CompanyStatus.ACTIVE, {"reason": "Wound up"}),
]


def upload_required_documents(company):
    for doc_type in LISTING_REQUIRED_DOCUMENTS:
        CompanyDocument.objects.create(
            company=company,
            document_type=doc_type,
            name=doc_type.label,
            external_url="https://files.example.test/doc",
            file_size=10,
            mime_type="application/pdf",
        )


class ApplicationNotificationProducerTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        self.bystander = User.objects.create_user(email="bystander@example.test", password="pw-12345678")
        self.company = Company.objects.create(owner=self.owner, name="Acme Pty Ltd", acn="123456789")
        self.task = patch(TASK).start()
        self.task.defer.side_effect = run_task  # run the deferred job inline so the row it writes is visible
        self.addCleanup(patch.stopall)

    def _set_status(self, status):
        Company.objects.filter(pk=self.company.pk).update(status=status)
        self.company.refresh_from_db()

    def rows(self, user):
        return Notification.objects.filter(user=user, notification_type="general")

    def test_matrix_covers_every_notified_transition(self):
        self.assertEqual({method for method, *_ in MATRIX}, set(APPLICANT_NOTIFICATIONS))

    def test_each_application_event_creates_one_row_and_defers_one_job_for_the_owner(self):
        for method, start, kwargs, title, body in MATRIX:
            with self.subTest(method=method):
                self._set_status(start)
                self.task.defer.reset_mock()
                Notification.objects.all().delete()

                transition_company(self.company, method, **kwargs)

                self.task.defer.assert_called_once_with(
                    user_id=str(self.owner.pk),
                    title=title,
                    body=body,
                    data={
                        "type": "company",
                        "event": method,
                        "company_id": str(self.company.uuid),
                        "status": self.company.status,
                    },
                    notification_type="general",
                )
                row = self.rows(self.owner).get()
                self.assertEqual((row.title, row.body), (title, body))
                self.assertFalse(self.rows(self.bystander).exists())

    def test_compliance_transitions_notify_nobody(self):
        for method, start, kwargs in SILENT:
            with self.subTest(method=method):
                self._set_status(start)
                transition_company(self.company, method, **kwargs)
        self.task.defer.assert_not_called()
        self.assertFalse(Notification.objects.exists())

    def test_a_refused_transition_defers_nothing(self):
        from companies.exceptions import InvalidStatusTransitionException

        with self.assertRaises(InvalidStatusTransitionException):
            transition_company(self.company, "approve")
        self.task.defer.assert_not_called()

    def test_a_job_that_cannot_be_deferred_rolls_the_transition_back(self):
        self._set_status(CompanyStatus.REVIEW)
        self.task.defer.side_effect = RuntimeError("queue down")

        with self.assertRaises(RuntimeError):
            transition_company(self.company, "approve", approved_by=self.owner)

        self.company.refresh_from_db()
        self.assertEqual((self.company.status, self.company.approved_at), (CompanyStatus.REVIEW, None))


@override_settings(STORAGES=TEST_STORAGES)
class ApplicationNotificationEntryPointsTest(APITestCase):
    """The admin button, the bulk action and the staff status route each announce a transition exactly once."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        self.staff = User.objects.create_superuser(email="staff@example.test", password="pw-12345678")
        self.company = Company.objects.create(owner=self.owner, name="Acme Pty Ltd", acn="123456789")
        self.task = patch(TASK).start()
        self.task.defer.side_effect = run_task
        self.addCleanup(patch.stopall)

    def _set_status(self, status):
        Company.objects.filter(pk=self.company.pk).update(status=status)
        self.company.refresh_from_db()

    def _titles(self):
        return list(Notification.objects.filter(user=self.owner).order_by("created_at").values_list("title", flat=True))

    def test_admin_transition_button(self):
        self._set_status(CompanyStatus.REVIEW)
        self.client.force_login(self.staff)

        url = reverse("admin:companies_company_transition", args=[self.company.uuid, "request-info"])
        self.client.post(url, {"reason": "Share register"})

        self.task.defer.assert_called_once()
        self.assertEqual(self._titles(), ["More information requested"])
        self.assertEqual(Notification.objects.get().body, "More information requested: Share register")

    def test_admin_bulk_approve_action(self):
        self._set_status(CompanyStatus.REVIEW)
        draft = Company.objects.create(owner=self.owner, name="Still draft", acn="333333333")
        admin = CompanyAdmin(Company, AdminSite())
        admin.message_user = lambda *args, **kwargs: None

        admin.approve_action(SimpleNamespace(user=self.staff), Company.objects.all())

        self.task.defer.assert_called_once()
        self.assertEqual(self._titles(), ["Application approved"])
        draft.refresh_from_db()
        self.assertEqual(draft.status, CompanyStatus.DRAFT)

    def test_staff_status_route(self):
        self._set_status(CompanyStatus.SUBMITTED)
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            f"/api/v1/companies/{self.company.uuid}/status/", {"status": "rejected", "reason": "No"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.task.defer.assert_called_once()
        self.assertEqual(self._titles(), ["Application rejected"])

    def test_owner_submit_resubmit_and_withdraw_routes(self):
        upload_required_documents(self.company)
        self.client.force_authenticate(self.owner)
        url = f"/api/v1/companies/{self.company.uuid}/"

        self.assertEqual(self.client.post(f"{url}submit/", {"confirm": True}, format="json").status_code, 200)
        self._set_status(CompanyStatus.INFO_REQUIRED)
        self.assertEqual(self.client.post(f"{url}resubmit/", {"response": "Done"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"{url}withdraw/", {}, format="json").status_code, 200)

        self.assertEqual(self.task.defer.call_count, 3)
        self.assertEqual(self._titles(), ["Application submitted", "Application resubmitted", "Application withdrawn"])


@skipUnless(connection.vendor == "postgresql", "procrastinate job rows live in PostgreSQL only")
class ApplicationNotificationJobRowTest(TestCase):
    """The real defer: one procrastinate_jobs row per event, none when the block fails after the defer."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Acme Pty Ltd", acn="123456789", status=CompanyStatus.REVIEW
        )

    def job_rows(self):
        return ProcrastinateJob.objects.filter(task_name=run_task.name)

    def test_approval_writes_one_todo_job_for_the_owner(self):
        transition_company(self.company, "approve", approved_by=self.owner)

        row = self.job_rows().get()
        self.assertEqual(row.status, "todo")
        self.assertEqual((row.args["user_id"], row.args["title"]), (str(self.owner.pk), "Application approved"))

    def test_a_failure_after_the_defer_rolls_the_job_row_back_with_the_status(self):
        original = Company.approve

        def approve_then_fail(company, **kwargs):
            original(company, **kwargs)
            raise RuntimeError("after the transition")

        with patch.object(Company, "approve", approve_then_fail):
            with self.assertRaises(RuntimeError):
                transition_company(self.company, "approve", approved_by=self.owner)

        self.assertEqual(self.job_rows().count(), 0)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.REVIEW)
