import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from documents.models import Document, DocumentType
from documents.services.document import create_document

User = get_user_model()

PDF_BYTES = b"%PDF-1.4 minimal"
UPLOAD_URL = "/api/v1/documents/"


class DocumentCreateAtomicityTest(APITransactionTestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.user = User.objects.create_user(email="doc-atomic@example.test", password="pw-12345678")
        self.client.force_authenticate(self.user)

    def _upload(self):
        return self.client.post(
            UPLOAD_URL,
            {
                "document_type": DocumentType.PAYSLIP,
                "file": SimpleUploadedFile("payslip.pdf", PDF_BYTES, content_type="application/pdf"),
            },
            format="multipart",
        )

    @patch("documents.services.document.extract_document.defer", side_effect=RuntimeError("queue down"))
    def test_a_failed_defer_leaves_no_document_behind(self, defer):
        response = self._upload()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(Document.objects.count(), 0)
        defer.assert_called_once()

    @patch("documents.services.document.extract_document.defer")
    def test_a_successful_upload_still_stores_the_row_and_defers_once(self, defer):
        response = self._upload()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(Document.objects.count(), 1)
        defer.assert_called_once_with(document_uuid=str(Document.objects.get().uuid))

    def test_the_task_is_deferred_from_inside_the_transaction_that_writes_the_row(self):
        seen = {}

        def record(**kwargs):
            connection = transaction.get_connection()
            seen["in_atomic_block"] = connection.in_atomic_block
            seen["rows_visible"] = Document.objects.count()

        with patch("documents.services.document.extract_document.defer", side_effect=record):
            create_document(
                self.user,
                {
                    "file": SimpleUploadedFile("payslip.pdf", PDF_BYTES, content_type="application/pdf"),
                    "document_type": DocumentType.PAYSLIP,
                    "mime_type": "application/pdf",
                },
            )

        self.assertTrue(seen["in_atomic_block"])
        self.assertEqual(seen["rows_visible"], 1)

    def test_a_caller_rolling_back_after_the_service_returns_takes_the_row_with_it(self):
        with patch("documents.services.document.extract_document.defer"):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    create_document(
                        self.user,
                        {
                            "file": SimpleUploadedFile("payslip.pdf", PDF_BYTES, content_type="application/pdf"),
                            "document_type": DocumentType.PAYSLIP,
                            "mime_type": "application/pdf",
                        },
                    )
                    raise RuntimeError("the caller fails after the service returned")

        self.assertEqual(Document.objects.count(), 0)
