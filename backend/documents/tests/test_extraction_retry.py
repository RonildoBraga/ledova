from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from procrastinate.jobs import Job

from documents.models import (
    Document,
    DocumentExtraction,
    DocumentType,
    ExtractionStatus,
)
from documents.services.extraction import ExtractionService
from documents.tasks.extract import extract_document
from integrations.llm_extract import (
    LlmExtractError,
    LlmExtractTransientError,
    LlmExtractValidationError,
)
from ledova_backend.procrastinate_app import app

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
        self.client_raising(LlmExtractTransientError())

        with self.assertRaises(LlmExtractTransientError):
            self.run_the_task()

    def test_the_attempt_is_recorded_before_the_exception_leaves_the_service(self):
        self.client_raising(LlmExtractTransientError())

        with self.assertRaises(LlmExtractTransientError):
            self.run_the_task()

        extraction = DocumentExtraction.objects.get(document=self.document)
        self.assertEqual(extraction.status, ExtractionStatus.FAILED)
        self.assertIn("LlmExtractTransientError", extraction.error)
        self.assertIsNotNone(extraction.finished_at)

    def test_output_the_schema_refuses_returns_rather_than_asking_the_model_again(self):
        self.client_raising(LlmExtractValidationError())

        answer = self.run_the_task()

        self.assertEqual(answer["status"], ExtractionStatus.FAILED)
        self.assertIn("LlmExtractValidationError", DocumentExtraction.objects.get(document=self.document).error)

    def test_a_permanent_upstream_failure_is_recorded_without_retrying(self):
        self.client_raising(LlmExtractError())

        answer = self.run_the_task()

        self.assertEqual(answer["status"], ExtractionStatus.FAILED)
        self.assertIn("LlmExtractError", DocumentExtraction.objects.get(document=self.document).error)

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
        self.client_raising(LlmExtractTransientError())

        for _ in range(3):
            with self.assertRaises(LlmExtractTransientError):
                self.run_the_task()

        self.assertEqual(DocumentExtraction.objects.filter(document=self.document).count(), 3)


class TheRetryStrategyGrantsTheAttemptsTest(TestCase):
    def test_a_raising_attempt_is_granted_a_second_and_a_third_and_no_fourth(self):
        strategy = extract_document.retry_strategy
        failure = LlmExtractTransientError()

        self.assertIsNotNone(strategy.get_retry_decision(exception=failure, job=a_job(0)))
        self.assertIsNotNone(strategy.get_retry_decision(exception=failure, job=a_job(1)))
        self.assertIsNone(strategy.get_retry_decision(exception=failure, job=a_job(2)))

    def test_the_retry_strategy_excludes_terminal_or_unclassified_failures(self):
        for error in (LlmExtractError(), LlmExtractValidationError(), ValueError("unsupported")):
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(extract_document.retry_strategy.get_retry_decision(exception=error, job=a_job(1)))

    def test_the_task_waits_thirty_seconds_before_retrying(self):
        self.assertEqual(extract_document.retry_strategy.wait, 30)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL worker queue")
class ExtractionWorkerRetryTest(TransactionTestCase):
    def setUp(self):
        user = User.objects.create_user(email="worker-extraction@example.test", password="pw-12345678")
        self.document = Document.objects.create(
            uploaded_by=user,
            document_type=DocumentType.PAYSLIP,
            original_filename="synthetic-payslip.pdf",
            mime_type="application/pdf",
        )

    def run_worker(self, effects):
        app.perform_import_paths()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM procrastinate_jobs")
            existing = {row[0] for row in cursor.fetchall()}
        queue = f"doc-{self.document.uuid.hex}"
        job_id = extract_document.configure(queue=queue).defer(document_uuid=str(self.document.uuid))
        self.addCleanup(self.remove_worker_job, job_id)
        with (
            patch.object(ExtractionService, "render_first_page", return_value=PAGE),
            patch("documents.services.extraction.LlmExtractClient") as client,
            patch.object(extract_document.retry_strategy, "wait", 0),
            patch.dict(app.periodic_registry.periodic_tasks, {}, clear=True),
            app.replace_connector(app.connector.get_worker_connector()),
        ):
            client.return_value.extract.side_effect = effects
            app.run_worker(
                queues=[queue],
                wait=False,
                listen_notify=False,
                install_signal_handlers=False,
                delete_jobs="never",
            )
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, attempts FROM procrastinate_jobs WHERE id = %s", [job_id])
            status, attempts = cursor.fetchone()
            cursor.execute("SELECT id FROM procrastinate_jobs")
            self.assertEqual({row[0] for row in cursor.fetchall()} - existing, {job_id})
        return {"status": status, "attempts": attempts}

    def remove_worker_job(self, job_id):
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM procrastinate_jobs WHERE id = %s", [job_id])

    def test_a_transient_failure_is_retried_until_the_third_attempt_then_fails(self):
        job = self.run_worker(LlmExtractTransientError())

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["attempts"], 3)
        self.assertEqual(self.document.extractions.count(), 3)
        self.assertEqual(set(self.document.extractions.values_list("status", flat=True)), {ExtractionStatus.FAILED})

    def test_a_retry_that_succeeds_keeps_the_failed_attempt_in_history(self):
        result = Mock(raw_output="{}", duration_ms=1, model_used="synthetic")
        result.parsed.model_dump.return_value = {"confidence": 0.9, "extraction_warnings": []}
        job = self.run_worker([LlmExtractTransientError(), result])

        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["attempts"], 2)
        self.assertEqual(
            list(self.document.extractions.order_by("created_at").values_list("status", flat=True)),
            [ExtractionStatus.FAILED, ExtractionStatus.SUCCEEDED],
        )

    def test_a_permanent_failure_finishes_after_one_recorded_attempt(self):
        job = self.run_worker(LlmExtractError())

        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["attempts"], 1)
        self.assertEqual(self.document.extractions.get().status, ExtractionStatus.FAILED)


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
