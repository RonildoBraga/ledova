import os
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from companies.models import Company, CompanyDocument, CompanyType
from companies.models import DocumentType as CompanyDocumentType
from documents.models import Document, DocumentType

User = get_user_model()

COMPANIES_BEFORE = ("companies", "0005_company_is_open_to_investors")
COMPANIES_AFTER = ("companies", "0006_company_document_private_storage")
DOCUMENTS_BEFORE = ("documents", "0001_initial")
DOCUMENTS_AFTER = ("documents", "0002_document_private_storage")

REAL_BYTES = b"%PDF-1.4 real bytes that must survive a rollback"
LONG_EXTENSION = "." + "e" * 30
WIDENED_LENGTH = 255
PREVIOUS_LENGTH = 100

_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("companies" in _migration_modules and _migration_modules["companies"] is None)


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)


def column_max_length(table, column):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return next(field.display_size for field in description if field.name == column)


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class PrivateStorageMigrationRoundTripTest(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest)

    def restore_latest(self):
        CompanyDocument.objects.all().delete()
        Document.objects.all().delete()
        migrate([COMPANIES_AFTER, DOCUMENTS_AFTER])

    @staticmethod
    def private_path(key):
        return os.path.join(settings.PRIVATE_MEDIA_ROOT, key)

    @staticmethod
    def public_path(key):
        return os.path.join(settings.MEDIA_ROOT, key)

    def make_company_document(self, label, acn, filename="constitution.pdf"):
        owner = User.objects.create_user(email=f"{label}@example.test", password="pw-12345678")
        company = Company.objects.create(
            owner=owner,
            name=f"{label} Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn=acn,
        )
        document = CompanyDocument.objects.create(
            company=company,
            document_type=CompanyDocumentType.CONSTITUTION,
            name="Constitution",
            file_size=len(REAL_BYTES),
            mime_type="application/pdf",
        )
        document.file.save(filename, ContentFile(REAL_BYTES), save=True)
        return document

    def make_user_document(self, label, filename="payslip.pdf"):
        owner = User.objects.create_user(email=f"{label}@example.test", password="pw-12345678")
        return Document.objects.create(
            uploaded_by=owner,
            document_type=DocumentType.PAYSLIP,
            original_filename="payslip.pdf",
            mime_type="application/pdf",
            file=ContentFile(REAL_BYTES, name=filename),
        )

    def assert_round_trip(self, before, after, table, present, widened, absent):
        for key in (present, widened):
            self.assertTrue(os.path.isfile(self.private_path(key)))
        os.remove(self.private_path(absent))
        self.assertGreater(len(widened), PREVIOUS_LENGTH)

        migrate([before])

        for key in (present, widened):
            self.assertFalse(os.path.isfile(self.private_path(key)))
            self.assertTrue(os.path.isfile(self.public_path(key)))
            with open(self.public_path(key), "rb") as handle:
                self.assertEqual(handle.read(), REAL_BYTES)
        self.assertFalse(os.path.exists(self.public_path(absent)))
        self.assertGreaterEqual(column_max_length(table, "file"), len(widened))

        migrate([after])

        for key in (present, widened):
            self.assertFalse(os.path.isfile(self.public_path(key)))
            self.assertTrue(os.path.isfile(self.private_path(key)))
            with open(self.private_path(key), "rb") as handle:
                self.assertEqual(handle.read(), REAL_BYTES)
        self.assertFalse(os.path.exists(self.private_path(absent)))
        self.assertEqual(column_max_length(table, "file"), WIDENED_LENGTH)

    def test_the_company_document_migration_round_trips_real_bytes(self):
        present = self.make_company_document("mig-company-present", "111000111").file.name
        widened = self.make_company_document("mig-company-widened", "111000222").file.name
        absent = self.make_company_document("mig-company-absent", "111000333").file.name

        self.assert_round_trip(
            COMPANIES_BEFORE,
            COMPANIES_AFTER,
            CompanyDocument._meta.db_table,
            present,
            widened,
            absent,
        )

    def test_the_user_document_migration_round_trips_real_bytes(self):
        present = self.make_user_document("mig-document-present").file.name
        widened = self.make_user_document("mig-document-widened", f"payslip{LONG_EXTENSION}").file.name
        absent = self.make_user_document("mig-document-absent").file.name

        self.assert_round_trip(
            DOCUMENTS_BEFORE,
            DOCUMENTS_AFTER,
            Document._meta.db_table,
            present,
            widened,
            absent,
        )

    def test_the_reverse_keeps_every_stored_key_readable_from_the_database(self):
        document = self.make_company_document("mig-company-keys", "111000444")
        key = document.file.name

        migrate([COMPANIES_BEFORE])

        document.refresh_from_db()
        self.assertEqual(document.file.name, key)

    def test_the_reverse_never_narrows_the_widened_column(self):
        self.make_company_document("mig-company-width", "111000555")
        self.make_user_document("mig-document-width", f"payslip{LONG_EXTENSION}")

        migrate([COMPANIES_BEFORE, DOCUMENTS_BEFORE])

        self.assertEqual(column_max_length(CompanyDocument._meta.db_table, "file"), WIDENED_LENGTH)
        self.assertEqual(column_max_length(Document._meta.db_table, "file"), WIDENED_LENGTH)
