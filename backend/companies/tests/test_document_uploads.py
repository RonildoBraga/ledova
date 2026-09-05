from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from companies.models import Company, CompanyDocument, CompanyType, DocumentType
from shared.uploads import MAX_UPLOAD_SIZE

User = get_user_model()


class CompanyDocumentUploadValidationTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="doc-owner@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.user, name="Doc Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="222333444"
        )
        self.client.force_authenticate(self.user)
        self.url = f"/api/v1/companies/{self.company.uuid}/documents/"

    def _post(self, upload):
        return self.client.post(
            self.url,
            {"document_type": DocumentType.ASIC_EXTRACT.value, "name": "Extract", "file": upload},
            format="multipart",
        )

    def test_a_pdf_within_the_cap_is_accepted_and_its_size_and_mime_are_captured(self):
        response = self._post(SimpleUploadedFile("extract.pdf", b"%PDF-1.4 body", content_type="application/pdf"))

        self.assertEqual(response.status_code, 201, response.content)
        document = CompanyDocument.objects.get(uuid=response.json()["uuid"])
        self.assertEqual(document.file_size, len(b"%PDF-1.4 body"))
        self.assertEqual(document.mime_type, "application/pdf")

    def test_png_and_jpeg_are_accepted(self):
        for name, mime in (("scan.png", "image/png"), ("scan.jpg", "image/jpeg")):
            with self.subTest(mime=mime):
                response = self._post(SimpleUploadedFile(name, b"bytes", content_type=mime))
                self.assertEqual(response.status_code, 201, response.content)

    def test_a_file_over_ten_megabytes_is_refused(self):
        oversized = SimpleUploadedFile("big.pdf", b"0" * (MAX_UPLOAD_SIZE + 1), content_type="application/pdf")

        response = self._post(oversized)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["file"], ["File size must not exceed 10 MB."])

    def test_a_disallowed_mime_type_is_refused(self):
        response = self._post(SimpleUploadedFile("notes.txt", b"text", content_type="text/plain"))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["file"], ["Only PDF and image files (PNG, JPEG) are allowed."])

    def test_a_disallowed_extension_is_refused_even_with_an_allowed_mime_type(self):
        response = self._post(SimpleUploadedFile("payload.exe", b"bytes", content_type="application/pdf"))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["file"], ["Only .pdf, .png, .jpg, .jpeg files are allowed."])

    def test_neither_a_file_nor_a_url_is_refused(self):
        response = self.client.post(
            self.url, {"document_type": DocumentType.ASIC_EXTRACT.value, "name": "Extract"}, format="multipart"
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_external_url_still_requires_its_size_and_mime_type(self):
        response = self.client.post(
            self.url,
            {
                "document_type": DocumentType.ASIC_EXTRACT.value,
                "name": "Extract",
                "external_url": "https://docs.example.test/extract",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("fileSize", response.json())
