import importlib
import os
import re
from itertools import count

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import clear_url_caches, reverse
from rest_framework.test import APIClient, APITestCase

from authentication.services import TokenService
from companies.admin.company import CompanyDocumentInline
from companies.models import Company, CompanyDocument, CompanyType, DocumentType

User = get_user_model()
MARKER = b"%PDF-1.4 ledova-company-document-marker"
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
_sequence = count(1)


def make_company(label):
    user = User.objects.create_user(
        email=f"{label}@documents.example.test", password="pw-12345678", is_active=True, is_email_verified=True
    )
    company = Company.objects.create(
        owner=user,
        name=f"{label} Pty Ltd",
        company_type=CompanyType.PROPRIETARY,
        acn=f"{next(_sequence):09d}",
    )
    return user, company


def make_document(company, payload=MARKER, **overrides):
    fields = {
        "company": company,
        "document_type": DocumentType.ASIC_EXTRACT,
        "name": "ASIC extract",
        "file_size": len(payload or b""),
        "mime_type": "application/pdf",
    }
    fields.update(overrides)
    document = CompanyDocument.objects.create(**fields)
    if payload is not None:
        document.file.save(f"{document.uuid}.pdf", ContentFile(payload), save=True)
    return document


def file_route(document):
    return f"/api/v1/companies/{document.company_id}/documents/{document.uuid}/file/"


class CompanyDocumentFileRouteTest(APITestCase):

    def setUp(self):
        self.owner, self.company = make_company("route-owner")
        self.other_user, self.other_company = make_company("route-other")
        self.document = make_document(self.company)
        self.url = file_route(self.document)

    @staticmethod
    def _streamed(response):
        return b"".join(response.streaming_content)

    def test_the_owner_reads_the_bytes_through_the_api(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(self._streamed(response), MARKER)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_it_streams_rather_than_redirecting_to_media(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertNotIn(response.status_code, (301, 302, 303, 307, 308))
        self.assertIsNone(response.headers.get("Location"))
        self.assertNotIn("/media/", response.headers.get("Content-Disposition", ""))

    def test_another_tenant_gets_404_and_not_403(self):
        self.client.force_authenticate(self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_another_tenant_naming_their_own_company_gets_404(self):
        self.client.force_authenticate(self.other_user)

        response = self.client.get(f"/api/v1/companies/{self.other_company.uuid}/documents/{self.document.uuid}/file/")

        self.assertEqual(response.status_code, 404)

    def test_an_anonymous_caller_gets_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_a_document_with_no_file_is_404(self):
        bare = make_document(
            self.company,
            payload=None,
            external_url="https://docs.example.test/extract",
            file_size=1,
        )
        self.client.force_authenticate(self.owner)

        self.assertEqual(self.client.get(file_route(bare)).status_code, 404)

    def test_the_serialised_url_is_the_authenticated_route_not_media(self):
        self.client.force_authenticate(self.owner)

        row = self.client.get(f"/api/v1/companies/{self.company.uuid}/documents/").json()["results"][0]

        self.assertIn(self.url, row["fileUrl"])
        self.assertNotIn("/media/", row["fileUrl"])

    def test_a_document_with_an_external_url_and_no_file_keeps_the_issuers_link(self):
        make_document(
            self.company,
            payload=None,
            document_type=DocumentType.PROSPECTUS,
            external_url="https://issuer.example.test/prospectus.pdf",
            file_size=1,
        )
        self.client.force_authenticate(self.owner)

        rows = self.client.get(
            f"/api/v1/companies/{self.company.uuid}/documents/?document_type={DocumentType.PROSPECTUS.value}"
        ).json()["results"]

        self.assertEqual([row["fileUrl"] for row in rows], ["https://issuer.example.test/prospectus.pdf"])

    def test_an_upload_answers_with_the_authenticated_route(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            f"/api/v1/companies/{self.company.uuid}/documents/",
            {
                "document_type": DocumentType.CONSTITUTION.value,
                "name": "Constitution",
                "file": SimpleUploadedFile("constitution.pdf", MARKER, content_type="application/pdf"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.content)
        uploaded = CompanyDocument.objects.get(uuid=response.json()["uuid"])
        self.assertNotIn("/media/", response.json()["fileUrl"])
        self.assertIn(file_route(uploaded), response.json()["fileUrl"])
        self.assertEqual(b"".join(self.client.get(file_route(uploaded)).streaming_content), MARKER)


class CompanyDocumentCookieNavigationTest(APITestCase):

    def setUp(self):
        self.owner, self.company = make_company("cookie-owner")
        self.document = make_document(self.company)
        self.client = APIClient(enforce_csrf_checks=True)
        access, _ = TokenService.issue(self.owner)
        self.client.cookies[settings.AUTH_COOKIE["access"]] = access

    def test_a_plain_navigation_carrying_only_the_session_cookie_reads_the_bytes(self):
        response = self.client.get(file_route(self.document))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), MARKER)
        self.assertEqual(response.headers["Content-Disposition"].split(";")[0], "inline")

    def test_the_same_navigation_without_the_cookie_is_401(self):
        self.client.cookies.clear()

        self.assertEqual(self.client.get(file_route(self.document)).status_code, 401)


@override_settings(STORAGES=ADMIN_STORAGES)
class CompanyDocumentAdminTest(TestCase):

    def setUp(self):
        self.owner, self.company = make_company("admin-owner")
        self.staff = User.objects.create_superuser(email="document-staff@example.test", password="pw-12345678")
        self.document = make_document(self.company)

    def test_staff_read_the_same_bytes_through_the_admin(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:companies_companydocument_file", args=[self.document.uuid]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), MARKER)

    def test_the_admin_file_view_refuses_a_non_staff_caller(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("admin:companies_companydocument_file", args=[self.document.uuid]))

        self.assertIn(response.status_code, (302, 403))

    def test_the_change_page_links_to_the_streaming_view(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:companies_companydocument_change", args=[self.document.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            reverse("admin:companies_companydocument_file", args=[self.document.uuid]),
            response.content.decode(),
        )

    def test_the_inline_on_the_company_page_links_a_hosted_document_to_the_streaming_view(self):
        self.client.force_login(self.staff)
        linked = make_document(
            self.company,
            payload=None,
            document_type=DocumentType.PROSPECTUS,
            external_url="https://issuer.example.test/prospectus.pdf",
            file_size=1,
        )
        streaming_url = reverse("admin:companies_companydocument_file", args=[self.document.uuid])

        inline = CompanyDocumentInline(Company, admin.site)
        self.assertIn(streaming_url, inline.file_link(self.document))
        self.assertIn(linked.external_url, inline.file_link(linked))

        response = self.client.get(reverse("admin:companies_company_change", args=[self.company.pk]))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(streaming_url, body)
        self.assertIn(linked.external_url, body)
        self.assertEqual(re.findall(r'href="(/media/[^"]*)"', body), [])
        cells = re.findall(r'<td class="field-file_link">(.*?)</td>', body, re.S)
        self.assertEqual(sum(1 for cell in cells if streaming_url in cell), 1)

    def test_the_changelist_and_add_pages_render(self):
        self.client.force_login(self.staff)

        self.assertEqual(self.client.get(reverse("admin:companies_companydocument_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:companies_companydocument_add")).status_code, 200)


@override_settings(STORAGES=ADMIN_STORAGES)
class CompanyDocumentIsNotServedFromMediaTest(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(email="document-media@example.test", password="pw-12345678")
        _, company = make_company("media-leak")
        self.document = make_document(company)

    @staticmethod
    def _reloaded_urlconf():
        import ledova_backend.urls

        importlib.reload(ledova_backend.urls)
        clear_url_caches()

    def test_the_admin_change_page_prints_no_media_href(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("admin:companies_companydocument_change", args=[self.document.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(re.findall(r'href="(/media/[^"]*)"', response.content.decode()), [])

    def test_the_document_file_has_no_public_url_at_all(self):
        with self.assertRaises(ValueError):
            self.document.file.url

    def test_an_anonymous_caller_cannot_fetch_the_document_from_media_under_debug(self):
        media_path = f"{settings.MEDIA_URL}{self.document.file.name}"

        with override_settings(DEBUG=True, ALLOWED_HOSTS=["*"]):
            self._reloaded_urlconf()
            try:
                response = Client().get(media_path)
            finally:
                self._reloaded_urlconf()

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(MARKER, response.content)

    def test_the_document_bytes_live_outside_the_served_media_root(self):
        path = self.document.file.path

        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), MARKER)
        self.assertTrue(path.startswith(os.path.abspath(settings.PRIVATE_MEDIA_ROOT)))
        self.assertFalse(path.startswith(os.path.abspath(settings.MEDIA_ROOT)))
