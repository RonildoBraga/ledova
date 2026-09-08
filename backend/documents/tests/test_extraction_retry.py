from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from procrastinate.jobs import Job

from documents.models import (
    Document,
    DocumentExtraction,
    DocumentType,
    ExtractionStatus,
)
from documents.services.extraction import ExtractionService
from documents.tasks.extract import extract_document
from integrations.llm_extract import LlmExtractError, LlmExtractValidationError

User = get_user_model()

PAGE = b"\x89PNG rendered"


def a_job(attempts):
    return Job(
        id=1,
        task_name=extract_document.name,
        task_kwargs={},
        queue="default",
        lock=None,
        queueing_lock=None,
        attempts=attempts,
    )


class ExtractionFailureReachesTheWorkerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="extract@example.test", password="pw-12345678")
        self.document = Document.objects.create(
            uploaded_by=self.user,
            document_type=DocumentType.PAYSLIP,
            original_filename="payslip.pdf",
            mime_type="application/pdf",
        )
        render = patch.object(ExtractionService, "render_first_page", return_value=PAGE)
        render.start()
        self.addCleanup(render.stop)

    def run_the_task(self):
        return extract_document(document_uuid=str(self.document.uuid))

    def client_raising(self, error):
        client = patch("documents.services.extraction.LlmExtractClient")
        made = client.start()
        self.addCleanup(client.stop)
        made.return_value.extract.side_effect = error
        return made

    def test_an_upstream_failure_leaves_the_task_raising_so_the_worker_can_retry(self):
        self.client_raising(LlmExtractError())

        with self.assertRaises(LlmExtractError):
            self.run_the_task()

    def test_the_attempt_is_recorded_before_the_exception_leaves_the_service(self):
        self.client_raising(LlmExtractError())

        with self.assertRaises(LlmExtractError):
            self.run_the_task()

        extraction = DocumentExtraction.objects.get(document=self.document)
        self.assertEqual(extraction.status, ExtractionStatus.FAILED)
        self.assertIn("LlmExtractError", extraction.error)
        self.assertIsNotNone(extraction.finished_at)

    def test_output_the_schema_refuses_returns_rather_than_asking_the_model_again(self):
        self.client_raising(LlmExtractValidationError())

        answer = self.run_the_task()

        self.assertEqual(answer["status"], ExtractionStatus.FAILED)
        self.assertIn("LlmExtractValidationError", DocumentExtraction.objects.get(document=self.document).error)

    def test_a_document_type_with_no_prompt_returns_rather_than_retrying(self):
        self.document.document_type = "not_a_type_the_service_knows"
        self.document.save(update_fields=["document_type"])

        answer = self.run_the_task()

        self.assertEqual(answer["status"], ExtractionStatus.FAILED)
        self.assertIn("Unsupported document_type", DocumentExtraction.objects.get(document=self.document).error)

    def test_a_missing_document_returns_rather_than_retrying(self):
        answer = extract_document(document_uuid="00000000-0000-0000-0000-000000000000")

        self.assertEqual(answer, {"status": "error", "error": "document_not_found"})

    def test_each_upstream_attempt_writes_its_own_row(self):
        self.client_raising(LlmExtractError())

        for _ in range(3):
            with self.assertRaises(LlmExtractError):
                self.run_the_task()

        self.assertEqual(DocumentExtraction.objects.filter(document=self.document).count(), 3)


class TheRetryStrategyGrantsTheAttemptsTest(TestCase):
    def test_a_raising_attempt_is_granted_a_second_and_a_third_and_no_fourth(self):
        strategy = extract_document.retry_strategy
        failure = LlmExtractError()

        self.assertIsNotNone(strategy.get_retry_decision(exception=failure, job=a_job(1)))
        self.assertIsNotNone(strategy.get_retry_decision(exception=failure, job=a_job(2)))
        self.assertIsNone(strategy.get_retry_decision(exception=failure, job=a_job(3)))

    def test_the_task_still_carries_the_strategy_the_issue_was_written_against(self):
        self.assertEqual(extract_document.retry_strategy.max_attempts, 3)
        self.assertEqual(extract_document.retry_strategy.wait, 30)


class RerunningAFailedExtractionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="rerun@example.test", password="pw-12345678")
        self.document = Document.objects.create(
            uploaded_by=self.user,
            document_type=DocumentType.PAYSLIP,
            original_filename="payslip.pdf",
            mime_type="application/pdf",
        )

    def admin(self):
        from django.contrib import admin as django_admin

        from documents.admin.extraction import DocumentExtractionAdmin

        return DocumentExtractionAdmin(DocumentExtraction, django_admin.site)

    def an_extraction(self, status):
        return DocumentExtraction.objects.create(document=self.document, status=status)

    def test_a_failed_attempt_is_queued_again(self):
        self.an_extraction(ExtractionStatus.FAILED)
        instance = self.admin()

        with patch("documents.tasks.extract_document.defer") as defer:
            with patch.object(instance, "message_user"):
                instance.rerun_extraction(None, DocumentExtraction.objects.all())

        defer.assert_called_once_with(document_uuid=str(self.document.uuid))

    def test_two_failed_attempts_on_one_document_queue_it_once(self):
        self.an_extraction(ExtractionStatus.FAILED)
        self.an_extraction(ExtractionStatus.FAILED)
        instance = self.admin()

        with patch("documents.tasks.extract_document.defer") as defer:
            with patch.object(instance, "message_user"):
                instance.rerun_extraction(None, DocumentExtraction.objects.all())

        defer.assert_called_once_with(document_uuid=str(self.document.uuid))

    def test_a_succeeded_attempt_is_refused_rather_than_re_extracted(self):
        self.an_extraction(ExtractionStatus.SUCCEEDED)
        instance = self.admin()

        with patch("documents.tasks.extract_document.defer") as defer:
            with patch.object(instance, "message_user") as told:
                instance.rerun_extraction(None, DocumentExtraction.objects.all())

        defer.assert_not_called()
        self.assertEqual(told.call_args.kwargs["level"], "warning")
