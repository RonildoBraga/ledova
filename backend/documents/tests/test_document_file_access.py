import importlib
import os
import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import clear_url_caches, reverse
from rest_framework.test import APITestCase

from documents.models import Document, DocumentType
from shared.tests.upload_fixtures import StubUploadDependencies, pdf_bytes
from shared.uploads import MAX_UPLOAD_SIZE

User = get_user_model()

DOCUMENT_BYTES = pdf_bytes()
SCRIPT_BYTES = b"<html><script>alert(document.cookie)</script></html>"
PASSWORD = "pw-12345678"
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "private": {"BACKEND": "shared.storage.PrivateMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def make_user(label, **privileges):
    return User.objects.create_user(
        email=f"{label}@example.test",
        password=PASSWORD,
        is_active=True,
        is_email_verified=True,
        **privileges,
    )


def make_document(user, filename="payslip.pdf", payload=DOCUMENT_BYTES):
    return Document.objects.create(
        uploaded_by=user,
        document_type=DocumentType.PAYSLIP,
        original_filename=filename,
        mime_type="application/pdf",
        file=ContentFile(payload, name=filename),
    )


class DocumentFileRouteTest(APITestCase):

    def setUp(self):
        self.owner = make_user("doc-file-owner")
        self.stranger = make_user("doc-file-stranger")
        self.staff = User.objects.create_superuser(email="doc-file-staff@example.test", password=PASSWORD)
        self.document = make_document(self.owner)
        self.url = f"/api/v1/documents/{self.document.uuid}/file/"

    @staticmethod
    def _streamed(response):
        return b"".join(response.streaming_content)

    def test_the_owner_reads_their_own_file(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(self._streamed(response), DOCUMENT_BYTES)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_the_download_keeps_the_original_filename(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertIn('filename="payslip.pdf"', response.headers["Content-Disposition"])

    def test_another_user_gets_404_not_403(self):
        self.client.force_authenticate(self.stranger)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_a_staff_caller_who_did_not_upload_it_gets_404(self):
        self.client.force_authenticate(self.staff)

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_an_anonymous_caller_gets_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_it_streams_rather_than_redirecting_to_media(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertNotIn(response.status_code, (301, 302, 303, 307, 308))
        self.assertIsNone(response.headers.get("Location"))
        self.assertNotIn("/media/", response.headers.get("Content-Disposition", ""))

    def test_the_route_reverses_under_the_documents_namespace(self):
        url = reverse("documents:documents-file", kwargs={"uuid": self.document.uuid})

        self.assertEqual(url, f"/api/v1/documents/{self.document.uuid}/file/")


class DocumentFileUrlTest(StubUploadDependencies, APITestCase):

    def setUp(self):
        self.owner = make_user("doc-url-owner")
        self.client.force_authenticate(self.owner)

    def test_the_serializer_hands_out_the_authenticated_route_not_a_media_path(self):
        document = make_document(self.owner)

        response = self.client.get(f"/api/v1/documents/{document.uuid}/")

        self.assertEqual(response.status_code, 200)
        file_url = response.json()["fileUrl"]
        self.assertIn(f"/api/v1/documents/{document.uuid}/file/", file_url)
        self.assertNotIn("/media/", file_url)

    @patch("documents.services.document.extract_document.defer")
    def test_an_upload_reports_the_same_route(self, _defer):
        response = self.client.post(
            "/api/v1/documents/",
            {
                "document_type": DocumentType.PAYSLIP.value,
                "file": SimpleUploadedFile("payslip.pdf", DOCUMENT_BYTES, content_type="application/pdf"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertIn(f"/api/v1/documents/{body['uuid']}/file/", body["fileUrl"])
        self.assertNotIn("/media/", body["fileUrl"])

    def test_the_stored_key_names_neither_the_uploader_nor_the_original_filename(self):
        document = make_document(self.owner, filename="jane-smith-payslip-march.pdf")

        self.assertNotIn("jane-smith-payslip-march", document.file.name)
        self.assertNotIn(f"/{self.owner.pk}/", document.file.name)
        self.assertTrue(document.file.name.startswith(f"documents/{document.uuid}/"))


class DocumentUploadAllowlistTest(StubUploadDependencies, APITestCase):

    def setUp(self):
        self.owner = make_user("doc-allowlist-owner")
        self.client.force_authenticate(self.owner)

    def _upload(self, filename, content_type, payload=DOCUMENT_BYTES):
        return self.client.post(
            "/api/v1/documents/",
            {
                "document_type": DocumentType.PAYSLIP.value,
                "file": SimpleUploadedFile(filename, payload, content_type=content_type),
            },
            format="multipart",
        )

    def test_an_html_upload_is_refused(self):
        response = self._upload("payslip.html", "text/html", SCRIPT_BYTES)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_a_pdf_name_carrying_an_html_content_type_is_refused(self):
        response = self._upload("payslip.pdf", "text/html", SCRIPT_BYTES)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_an_svg_upload_is_refused(self):
        response = self._upload("payslip.svg", "image/svg+xml", SCRIPT_BYTES)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    def test_an_oversized_upload_is_refused(self):
        response = self._upload("payslip.pdf", "application/pdf", b"x" * (MAX_UPLOAD_SIZE + 1))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Document.objects.count(), 0)

    @patch("documents.services.document.extract_document.defer")
    def test_a_pdf_upload_is_stored_with_the_allowlisted_mime_type(self, _defer):
        response = self._upload("payslip.pdf", "application/pdf")

        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(Document.objects.get().mime_type, "application/pdf")


@override_settings(STORAGES=ADMIN_STORAGES)
class DocumentIsNotServedFromMediaTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(email="doc-media-staff@example.test", password=PASSWORD)
        self.owner = make_user("doc-media-owner")
        self.document = make_document(self.owner)

    @staticmethod
    def _reloaded_urlconf():
        import ledova_backend.urls

        importlib.reload(ledova_backend.urls)
        clear_url_caches()

    def test_the_document_file_has_no_public_url_at_all(self):
        with self.assertRaises(ValueError):
            self.document.file.url

    def test_the_document_bytes_live_outside_the_served_media_root(self):
        path = self.document.file.path

        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.startswith(os.path.abspath(settings.PRIVATE_MEDIA_ROOT)))
        self.assertFalse(path.startswith(os.path.abspath(settings.MEDIA_ROOT)))

    def test_an_anonymous_caller_cannot_fetch_the_document_from_media_under_debug(self):
        media_path = f"{settings.MEDIA_URL}{self.document.file.name}"

        with override_settings(DEBUG=True, ALLOWED_HOSTS=["*"]):
            self._reloaded_urlconf()
            try:
                response = Client().get(media_path)
            finally:
                self._reloaded_urlconf()

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(DOCUMENT_BYTES, response.content)

    def test_the_document_admin_change_page_prints_no_media_href(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:documents_document_change", args=[self.document.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(re.findall(r'href="(/media/[^"]*)"', response.content.decode()), [])

    def test_the_admin_route_hands_back_the_original_filename(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:documents_document_file", args=[self.document.uuid]))

        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="payslip.pdf"', response.headers["Content-Disposition"])

    def test_the_document_admin_change_page_links_the_streaming_route(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:documents_document_change", args=[self.document.pk]))

        self.assertIn(
            reverse("admin:documents_document_file", args=[self.document.uuid]),
            response.content.decode(),
        )
