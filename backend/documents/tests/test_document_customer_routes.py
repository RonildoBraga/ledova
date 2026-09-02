import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from documents.models import (
    Document,
    DocumentExtraction,
    DocumentType,
    ExtractionStatus,
)

User = get_user_model()


class DocumentCustomerRouteTest(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.foreign_user = self._make_user("documents-foreign")
        self.foreign_document = self._make_document(self.foreign_user, "foreign")
        self.foreign_extraction = self._make_extraction(
            self.foreign_document,
            "foreign-latest",
            ExtractionStatus.SUCCEEDED,
        )
        self.actor_cases = (
            self._make_actor_case("documents-regular"),
            self._make_actor_case("documents-staff", is_staff=True),
            self._make_actor_case("documents-super", is_superuser=True, is_staff=True),
        )

    def _make_user(self, label, **privileges):
        return User.objects.create_user(
            email=f"{label}@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
            **privileges,
        )

    @staticmethod
    def _make_document(user, label):
        return Document.objects.create(
            uploaded_by=user,
            document_type=DocumentType.PAYSLIP,
            original_filename=f"{label}.pdf",
            mime_type="application/pdf",
            file=f"documents/fixtures/{label}.pdf",
            note=f"Document note {label}",
        )

    @staticmethod
    def _make_extraction(document, label, status):
        return DocumentExtraction.objects.create(
            document=document,
            status=status,
            model_name=f"model-{label}",
            parsed_json={"label": label},
            confidence=0.9,
            warnings=[],
        )

    def _make_actor_case(self, label, **privileges):
        actor = self._make_user(label, **privileges)
        document = self._make_document(actor, label)
        older_extraction = self._make_extraction(
            document,
            f"{label}-older",
            ExtractionStatus.FAILED,
        )
        latest_extraction = self._make_extraction(
            document,
            f"{label}-latest",
            ExtractionStatus.SUCCEEDED,
        )
        return actor, document, older_extraction, latest_extraction

    @staticmethod
    def _response_rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_reads_expose_only_the_latest_extraction(self):
        actor, document, older_extraction, latest_extraction = self.actor_cases[0]
        self.client.force_authenticate(actor)

        list_response = self.client.get("/api/v1/documents/")
        self.assertEqual(list_response.status_code, 200)
        rows = self._response_rows(list_response)
        self.assertEqual({row["uuid"] for row in rows}, {str(document.uuid)})
        self.assertEqual(rows[0]["latestExtraction"]["uuid"], str(latest_extraction.uuid))
        self.assertNotEqual(rows[0]["latestExtraction"]["uuid"], str(older_extraction.uuid))

        detail_response = self.client.get(f"/api/v1/documents/{document.uuid}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["latestExtraction"]["uuid"], str(latest_extraction.uuid))

    def test_delete_removes_the_document_and_its_extractions(self):
        actor, _, _, _ = self.actor_cases[0]
        self.client.force_authenticate(actor)
        disposable = self._make_document(actor, "disposable")
        disposable_extraction = self._make_extraction(disposable, "disposable", ExtractionStatus.PENDING)

        delete_response = self.client.delete(f"/api/v1/documents/{disposable.uuid}/")

        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Document.objects.filter(uuid=disposable.uuid).exists())
        self.assertFalse(DocumentExtraction.objects.filter(uuid=disposable_extraction.uuid).exists())

    @patch("documents.views.document.extract_document.defer")
    def test_multipart_upload_is_server_bound_for_every_role(self, defer_task):
        for index, (actor, _, _, _) in enumerate(self.actor_cases):
            self.client.force_authenticate(actor)
            upload = SimpleUploadedFile(
                f"upload-{index}.pdf",
                b"%PDF-1.4\nminimal test document\n",
                content_type="application/pdf",
            )

            response = self.client.post(
                "/api/v1/documents/",
                {
                    "documentType": DocumentType.PAYSLIP,
                    "note": f"Upload by {actor.email}",
                    "file": upload,
                },
                format="multipart",
            )

            with self.subTest(actor=actor.email):
                self.assertEqual(response.status_code, 202)
                document = Document.objects.get(uuid=response.json()["uuid"])
                self.assertEqual(document.uploaded_by, actor)
                self.assertEqual(document.original_filename, f"upload-{index}.pdf")
                self.assertEqual(document.mime_type, "application/pdf")
                self.assertTrue(document.file.storage.exists(document.file.name))
                self.assertFalse(document.extractions.exists())
                defer_task.assert_called_once_with(document_uuid=str(document.uuid))

            defer_task.reset_mock()

    def test_anonymous_requests_are_rejected(self):
        self.client.force_authenticate(user=None)

        list_response = self.client.get("/api/v1/documents/")
        detail_response = self.client.get(f"/api/v1/documents/{self.foreign_document.uuid}/")

        self.assertEqual(list_response.status_code, 401)
        self.assertEqual(detail_response.status_code, 401)

    def test_update_methods_are_not_available(self):
        actor, document, _, _ = self.actor_cases[0]
        self.client.force_authenticate(actor)

        put_response = self.client.put(
            f"/api/v1/documents/{document.uuid}/",
            {"note": "Replacement"},
            format="json",
        )
        patch_response = self.client.patch(
            f"/api/v1/documents/{document.uuid}/",
            {"note": "Replacement"},
            format="json",
        )

        self.assertEqual(put_response.status_code, 405)
        self.assertEqual(patch_response.status_code, 405)
        document.refresh_from_db()
        self.assertNotEqual(document.note, "Replacement")
