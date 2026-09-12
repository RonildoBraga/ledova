import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from documents.models import Document, DocumentExtraction, ExtractionStatus
from documents.services.document import create_document
from documents.tasks.extract import extract_document
from documents.tests.test_supporting_evidence import STORAGES
from ledova_backend.procrastinate_app import app
from shared.db import (
    APP_ALIAS,
    OPERATOR_ALIAS,
    current_alias,
    principal_of,
    use_operator,
)
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant

TABLES = ("documents", "document_extractions")


@override_settings(STORAGES=STORAGES)
class ScopedDocumentExtractionTest(RunsOnTheScopedConnection, TransactionTestCase):
    def setUp(self):
        super().setUp()
        with use_operator():
            self.uploader = make_tenant("scoped-extract-owner")
            self.other = make_tenant("scoped-extract-other")
        render = patch("documents.services.extraction.ExtractionService.render_first_page", return_value=b"image")
        self.addCleanup(render.stop)
        render.start()
        client = patch("documents.services.extraction.LlmExtractClient")
        self.addCleanup(client.stop)
        self.extract = client.start().return_value.extract
        self.extract.return_value = SimpleNamespace(
            parsed=SimpleNamespace(model_dump=lambda mode: {"confidence": 0.9, "extraction_warnings": []}),
            raw_output="{}",
            duration_ms=12,
            model_used="synthetic-model",
        )

    def run_task(self, **payload):
        with use_operator():
            result = extract_document.func(**payload)
            self.assertEqual(current_alias(), OPERATOR_ALIAS)
        self.assertIn(principal_of(APP_ALIAS), (None, ""))
        return result

    def recorder(self, calls):
        def execute(execute, sql, params, many, context):
            for table in TABLES:
                if f'"{table}"' in sql:
                    calls.append((context["connection"].alias, sql.split()[0], table))
            return execute(sql, params, many, context)

        return execute

    def extractions_of(self, tenant):
        with use_operator():
            return list(DocumentExtraction.objects.filter(document=tenant.document))

    def test_the_uploaders_principal_carries_every_read_write_and_retention_recheck(self):
        observed = []

        def extract(**kwargs):
            self.assertEqual(current_alias(), APP_ALIAS)
            with connections[current_alias()].cursor() as cursor:
                cursor.execute("SELECT current_user, current_setting('app.user_id', true)")
                self.assertEqual(cursor.fetchone(), (settings.RLS_ROLES[APP_ALIAS], str(self.uploader.user.pk)))
            self.assertEqual(set(Document.objects.values_list("pk", flat=True)), {self.uploader.document.pk})
            return self.extract.return_value

        self.extract.side_effect = extract
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.recorder(observed)))
            result = self.run_task(document_uuid=str(self.uploader.document.pk), principal_id=self.uploader.user.pk)

        self.assertEqual(result["status"], ExtractionStatus.SUCCEEDED)
        self.assertEqual({alias for alias, _, _ in observed}, {APP_ALIAS})
        self.assertLessEqual(
            {("SELECT", "documents"), ("INSERT", "document_extractions")},
            {(operation, table) for _, operation, table in observed},
        )
        self.assertEqual(len(self.extractions_of(self.uploader)), 1)
        self.assertEqual(self.extractions_of(self.other), [])

    def test_another_uploaders_document_is_refused_before_any_extraction_row(self):
        observed = []
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.recorder(observed)))
            result = self.run_task(document_uuid=str(self.other.document.pk), principal_id=self.uploader.user.pk)

        self.assertEqual(result, {"status": "error", "error": "document_not_found"})
        self.assertEqual({alias for alias, _, _ in observed}, {APP_ALIAS})
        self.extract.assert_not_called()
        self.assertEqual(self.extractions_of(self.other), [])
        with use_operator():
            self.assertTrue(Document.objects.filter(pk=self.other.document.pk).exists())

    def test_the_staff_rerun_choice_reaches_a_document_it_does_not_own(self):
        result = self.run_task(document_uuid=str(self.other.document.pk), principal_id=None)
        self.assertEqual(result["status"], ExtractionStatus.SUCCEEDED)
        self.assertEqual(len(self.extractions_of(self.other)), 1)

    def test_retention_withdrawn_between_enqueue_and_run_skips_under_the_uploader(self):
        with use_operator():
            Document.objects.filter(pk=self.uploader.document.pk).update(purged_at=timezone.now())
        observed = []
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.recorder(observed)))
            result = self.run_task(document_uuid=str(self.uploader.document.pk), principal_id=self.uploader.user.pk)

        self.assertEqual(result, {"status": "skipped", "reason": "document_unavailable"})
        self.assertEqual({alias for alias, _, _ in observed}, {APP_ALIAS})
        self.extract.assert_not_called()
        self.assertEqual(self.extractions_of(self.uploader), [])

    def queued(self):
        with use_operator(), connections[OPERATOR_ALIAS].cursor() as cursor:
            cursor.execute("SELECT id, task_name, args FROM procrastinate_jobs ORDER BY id")
            rows = cursor.fetchall()
        return {r[0]: (r[1], r[2] if isinstance(r[2], dict) else json.loads(r[2])) for r in rows}

    def delete_jobs(self, identifiers):
        with use_operator(), connections[OPERATOR_ALIAS].cursor() as cursor:
            for identifier in identifiers:
                cursor.execute("DELETE FROM procrastinate_jobs WHERE id = %s", [identifier])

    def test_the_upload_producer_captures_the_uploader_as_the_principal(self):
        before = self.queued()
        with use_operator():
            document = create_document(
                self.uploader.user,
                {
                    "file": self.uploader.document.file,
                    "mime_type": "application/pdf",
                    "document_type": "payslip",
                },
            )
        jobs = {key: row for key, row in self.queued().items() if key not in before}
        self.addCleanup(self.delete_jobs, list(jobs))
        self.assertEqual(len(jobs), 1)
        name, args = next(iter(jobs.values()))
        self.assertEqual(name, extract_document.name)
        self.assertEqual(set(args), {"document_uuid", "principal_id"})
        self.assertEqual(args["document_uuid"], str(document.uuid))
        self.assertEqual(args["principal_id"], self.uploader.user.pk)

    def test_a_deferred_job_without_a_principal_is_refused_rather_than_run_unscoped(self):
        observed = []
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.recorder(observed)))
            with self.assertRaises(TypeError):
                with use_operator():
                    app.tasks[extract_document.name].func(document_uuid=str(self.other.document.pk))
        self.assertEqual(observed, [])
        self.extract.assert_not_called()
        self.assertEqual(self.extractions_of(self.other), [])
