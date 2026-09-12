import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from documents.models import Document, DocumentType
from documents.services.document import create_document

User = get_user_model()

PDF_BYTES = b"%PDF-1.4 minimal"


class DocumentVisibilityTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="doc-owner@example.test", password="pw-12345678")
        self.stranger = User.objects.create_user(email="doc-stranger@example.test", password="pw-12345678")
        self.document = Document.objects.create(
            uploaded_by=self.owner,
            document_type=DocumentType.PAYSLIP,
            original_filename="own.pdf",
            mime_type="application/pdf",
        )

    def test_the_uploader_sees_their_own_document(self):
        self.assertEqual(list(Document.objects.visible_to_user(self.owner)), [self.document])

    def test_another_user_sees_nothing(self):
        self.assertFalse(Document.objects.visible_to_user(self.stranger).exists())

    def test_an_anonymous_or_missing_caller_sees_nothing(self):
        self.assertFalse(Document.objects.visible_to_user(AnonymousUser()).exists())
        self.assertFalse(Document.objects.visible_to_user(None).exists())


class CreateDocumentServiceTest(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.user = User.objects.create_user(email="doc-service@example.test", password="pw-12345678")

    @patch("documents.services.document.extract_document.defer")
    def test_it_stores_the_upload_and_defers_extraction(self, defer):
        upload = SimpleUploadedFile("payslip.pdf", PDF_BYTES, content_type="application/pdf")

        document = create_document(
            self.user,
            {"file": upload, "document_type": DocumentType.PAYSLIP, "mime_type": "application/pdf"},
        )

        self.assertEqual(document.uploaded_by, self.user)
        self.assertEqual(document.original_filename, "payslip.pdf")
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertEqual(document.note, "")
        defer.assert_called_once_with(document_uuid=str(document.uuid), principal_id=self.user.pk)

    @patch("documents.services.document.extract_document.defer")
    def test_it_keeps_an_optional_note(self, defer):
        upload = SimpleUploadedFile("payslip.pdf", PDF_BYTES, content_type="application/pdf")

        document = create_document(
            self.user,
            {
                "file": upload,
                "document_type": DocumentType.PAYSLIP,
                "mime_type": "application/pdf",
                "note": "March",
            },
        )

        self.assertEqual(document.note, "March")
