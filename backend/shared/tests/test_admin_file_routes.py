from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from companies.models import Company, CompanyDocument, CompanyType
from companies.models import DocumentType as CompanyDocumentType
from documents.models import Document, DocumentType
from users.models import InvestorClassification
from users.tests.factories import attach_evidence, make_classification, make_investor

User = get_user_model()
PASSWORD = "pw-12345678"
FILE_BYTES = b"%PDF-1.4 admin route bytes"
HTML_BYTES = b"<html><script>alert(document.cookie)</script></html>"
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private": {"BACKEND": "shared.storage.PrivateMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def staff_user(label):
    return User.objects.create_user(
        email=f"{label}@example.test",
        password=PASSWORD,
        is_staff=True,
        is_active=True,
        is_email_verified=True,
    )


def grant_view(user, model):
    content_type = ContentType.objects.get_for_model(model)
    user.user_permissions.add(Permission.objects.get(content_type=content_type, codename=f"view_{content_type.model}"))


@override_settings(STORAGES=ADMIN_STORAGES)
class AdminFileRouteAuthorizationTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(email="admin-files@example.test", password=PASSWORD)
        self.routes = {
            CompanyDocument: self._company_document_route(),
            Document: self._document_route(),
            InvestorClassification: self._classification_route(),
        }

    def _company_document_route(self):
        owner = User.objects.create_user(email="admin-files-owner@example.test", password=PASSWORD)
        company = Company.objects.create(
            owner=owner,
            name="Admin Files Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="222333444",
        )
        document = CompanyDocument.objects.create(
            company=company,
            document_type=CompanyDocumentType.CONSTITUTION,
            name="Constitution",
            file_size=len(FILE_BYTES),
            mime_type="application/pdf",
        )
        document.file.save("constitution.pdf", ContentFile(FILE_BYTES), save=True)
        return reverse("admin:companies_companydocument_file", args=[document.uuid])

    def _document_route(self):
        uploader = User.objects.create_user(email="admin-files-uploader@example.test", password=PASSWORD)
        document = Document.objects.create(
            uploaded_by=uploader,
            document_type=DocumentType.PAYSLIP,
            original_filename="payslip.pdf",
            mime_type="application/pdf",
            file=ContentFile(FILE_BYTES, name="payslip.pdf"),
        )
        return reverse("admin:documents_document_file", args=[document.uuid])

    def _classification_route(self):
        _, account = make_investor("admin-files-investor")
        classification = attach_evidence(make_classification(account), FILE_BYTES)
        return reverse("admin:users_investorclassification_evidence", args=[classification.uuid])

    @staticmethod
    def _body(response):
        return b"".join(response.streaming_content) if response.streaming else response.content

    def test_a_superuser_reads_every_streaming_admin_route(self):
        self.client.force_login(self.superuser)

        for model, url in self.routes.items():
            with self.subTest(model=model.__name__):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self._body(response), FILE_BYTES)

    def test_staff_without_view_permission_are_refused_on_every_route(self):
        plain = staff_user("admin-files-plain")
        self.client.force_login(plain)

        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        for model, url in self.routes.items():
            with self.subTest(model=model.__name__):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 403)
                self.assertNotIn(FILE_BYTES, self._body(response))

    def test_an_anonymous_caller_is_redirected_to_the_admin_login(self):
        for model, url in self.routes.items():
            with self.subTest(model=model.__name__):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response.headers["Location"])

    def test_every_route_downloads_rather_than_rendering_in_the_admin_origin(self):
        self.client.force_login(self.superuser)

        for model, url in self.routes.items():
            with self.subTest(model=model.__name__):
                response = self.client.get(url)

                self.assertTrue(response.headers["Content-Disposition"].startswith("attachment;"))
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_a_row_whose_stored_mime_type_is_html_still_downloads(self):
        uploader = User.objects.create_user(email="admin-files-legacy@example.test", password=PASSWORD)
        document = Document.objects.create(
            uploaded_by=uploader,
            document_type=DocumentType.PAYSLIP,
            original_filename="payslip.html",
            mime_type="text/html",
            file=ContentFile(HTML_BYTES, name="payslip.html"),
        )
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("admin:documents_document_file", args=[document.uuid]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._body(response), HTML_BYTES)
        self.assertTrue(response.headers["Content-Disposition"].startswith("attachment;"))

    def test_the_permission_is_checked_per_model(self):
        for granted, url in self.routes.items():
            with self.subTest(model=granted.__name__):
                user = staff_user(f"admin-files-{granted.__name__.lower()}")
                grant_view(user, granted)
                self.client.force_login(user)

                self.assertEqual(self.client.get(url).status_code, 200)
                for other, other_url in self.routes.items():
                    if other is granted:
                        continue
                    self.assertEqual(self.client.get(other_url).status_code, 403)


@override_settings(STORAGES=ADMIN_STORAGES)
class ClassificationTransitionAuthorizationTest(TestCase):

    def setUp(self):
        _, account = make_investor("admin-transition-investor")
        self.classification = make_classification(account)
        self.url = reverse(
            "admin:users_investorclassification_transition",
            args=[self.classification.uuid, "verify"],
        )

    def test_staff_without_change_permission_cannot_open_a_transition(self):
        self.client.force_login(staff_user("admin-transition-plain"))

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_view_permission_alone_does_not_unlock_a_transition(self):
        user = staff_user("admin-transition-viewer")
        grant_view(user, InvestorClassification)
        self.client.force_login(user)

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_a_superuser_opens_the_transition_form(self):
        self.client.force_login(
            User.objects.create_superuser(email="admin-transition-super@example.test", password=PASSWORD)
        )

        self.assertEqual(self.client.get(self.url).status_code, 200)
