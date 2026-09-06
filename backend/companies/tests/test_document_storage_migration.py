import os
from unittest import skipUnless
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from companies.models import Company, CompanyDocument, CompanyType, DocumentType

User = get_user_model()
MIGRATE_FROM = [("companies", "0005_company_is_open_to_investors")]
MIGRATE_TO = [("companies", "0006_company_document_private_storage")]
MIGRATION_LOGGER = "companies.migrations.0006_company_document_private_storage"
MARKER = b"%PDF-1.4 ledova-relocated-document"
MISSING_NAME = "companies/gone/documents/asic/gone.pdf"
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("companies" in _migration_modules and _migration_modules["companies"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class CompanyDocumentPrivateStorageMigrationTest(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.public = storages["default"]
        self.private = storages["private"]
        self.names = []
        self.addCleanup(self.discard_files)
        self.addCleanup(self.restore_latest_schema)
        self.migrate(MIGRATE_FROM)
        owner = User.objects.create_user(email="migration-owner@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=owner, name="Migration Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="123123123"
        )

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)

    def restore_latest_schema(self):
        self.migrate(MIGRATE_TO)

    def discard_files(self):
        for name in self.names:
            self.public.delete(name)
            self.private.delete(name)

    def make_document(self, name, document_type=DocumentType.ASIC_EXTRACT):
        return CompanyDocument.objects.create(
            company=self.company,
            document_type=document_type,
            name="Extract",
            file=name,
            file_size=len(MARKER),
            mime_type="application/pdf",
        )

    def _fresh_name(self):
        name = f"companies/migrate/documents/asic/{uuid4()}.pdf"
        self.names.append(name)
        return name

    def public_document(self):
        name = self.public.save(self._fresh_name(), ContentFile(MARKER))
        return self.make_document(name), name

    def private_document(self):
        name = self.private.save(self._fresh_name(), ContentFile(MARKER))
        return self.make_document(name, document_type=DocumentType.CONSTITUTION), name

    @staticmethod
    def read(storage, name):
        with storage.open(name) as handle:
            return handle.read()

    def test_a_file_under_the_served_media_root_is_moved_and_still_reads(self):
        document, name = self.public_document()

        self.migrate(MIGRATE_TO)

        self.assertFalse(self.public.exists(name))
        self.assertTrue(self.private.exists(name))
        self.assertEqual(self.read(self.private, name), MARKER)
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, name)))
        self.assertEqual(CompanyDocument.objects.get(pk=document.pk).file.name, name)
        self.assertEqual(CompanyDocument.objects.get(pk=document.pk).file.read(), MARKER)

    def test_a_file_already_private_is_left_where_it_is(self):
        _, name = self.private_document()
        before = os.stat(os.path.join(settings.PRIVATE_MEDIA_ROOT, name))

        self.migrate(MIGRATE_TO)

        self.assertTrue(self.private.exists(name))
        self.assertFalse(self.public.exists(name))
        self.assertEqual(self.read(self.private, name), MARKER)
        after = os.stat(os.path.join(settings.PRIVATE_MEDIA_ROOT, name))
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))

    def test_a_row_whose_file_is_missing_from_disk_is_logged_and_skipped(self):
        document = self.make_document(MISSING_NAME)

        with self.assertLogs(MIGRATION_LOGGER, "WARNING") as logs:
            self.migrate(MIGRATE_TO)

        self.assertIn(str(document.uuid), logs.output[0])
        self.assertIn(MISSING_NAME, logs.output[0])
        self.assertFalse(self.private.exists(MISSING_NAME))
        self.assertFalse(self.public.exists(MISSING_NAME))
        self.assertEqual(CompanyDocument.objects.get(pk=document.pk).file.name, MISSING_NAME)

    def test_a_row_with_no_file_at_all_is_left_alone(self):
        document = self.make_document("")

        self.migrate(MIGRATE_TO)

        self.assertEqual(CompanyDocument.objects.get(pk=document.pk).file.name, "")

    def test_the_reverse_puts_the_bytes_back_under_the_media_root(self):
        _, name = self.public_document()

        self.migrate(MIGRATE_TO)
        self.migrate(MIGRATE_FROM)

        self.assertTrue(self.public.exists(name))
        self.assertFalse(self.private.exists(name))
        self.assertEqual(self.read(self.public, name), MARKER)
