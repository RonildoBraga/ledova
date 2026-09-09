import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import transaction
from django.db.models.signals import post_delete
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from companies.models import Company, CompanyDocument
from documents.models import Document, DocumentType
from shared.services.orphaned_files import GRACE, orphaned_files, sweep_orphaned_files
from shared.storage import (
    CONDITIONALLY_RETAINED,
    RETAINED_AFTER_ROW_DELETE,
    RETAINED_STORAGE_PREFIXES,
    SWEPT_STORAGE_PREFIXES,
    private_file_fields,
    private_storage,
    swept_file_fields,
)
from users.models import UserAccount
from users.models.investor_classification import InvestorClassification

User = get_user_model()

PDF = b"%PDF-1.4 minimal"


class PrivateFileFieldCoverageTest(TestCase):
    def test_every_private_file_field_is_either_swept_or_declared_retained(self):
        undeclared = [
            f"{model._meta.label}.{field_name}"
            for model, field_name in private_file_fields()
            if model._meta.label not in RETAINED_AFTER_ROW_DELETE
            and (model, field_name) not in set(swept_file_fields())
        ]

        self.assertEqual(undeclared, [])

    def test_a_retained_model_carries_a_reason_and_is_not_swept(self):
        swept_labels = {model._meta.label for model, _ in swept_file_fields()}

        for label, reason in RETAINED_AFTER_ROW_DELETE.items():
            with self.subTest(label=label):
                self.assertEqual(label in swept_labels, label in CONDITIONALLY_RETAINED)
                self.assertGreater(len(reason), 40)

    def test_the_swept_and_retained_prefixes_do_not_overlap(self):
        self.assertEqual(set(SWEPT_STORAGE_PREFIXES) & set(RETAINED_STORAGE_PREFIXES), set())

    @staticmethod
    def _unsaved_probe(model):
        instance = model()
        for field in model._meta.fields:
            if not field.is_relation or field.related_model is None:
                continue
            related = field.related_model()
            if any(f.name == "uuid" for f in field.related_model._meta.fields):
                related.uuid = uuid4()
            setattr(instance, field.name, related)
        return instance

    def _declared_prefix_of(self, model, field_name):
        field = model._meta.get_field(field_name)
        return field.generate_filename(self._unsaved_probe(model), "probe.pdf").split("/", 1)[0]

    def test_every_private_file_field_writes_under_a_declared_prefix(self):
        declared = set(SWEPT_STORAGE_PREFIXES) | set(RETAINED_STORAGE_PREFIXES)
        undeclared = [
            f"{model._meta.label}.{field_name} -> {self._declared_prefix_of(model, field_name)}/"
            for model, field_name in private_file_fields()
            if self._declared_prefix_of(model, field_name) not in declared
        ]

        self.assertEqual(undeclared, [])

    def test_a_retained_model_writes_under_a_retained_prefix_and_a_swept_one_does_not(self):
        for model, field_name in private_file_fields():
            with self.subTest(model=model._meta.label):
                prefix = self._declared_prefix_of(model, field_name)
                retained = model._meta.label in RETAINED_AFTER_ROW_DELETE
                self.assertEqual(prefix in RETAINED_STORAGE_PREFIXES, retained)
                self.assertEqual(prefix in SWEPT_STORAGE_PREFIXES, not retained)

    def test_conditionally_retained_files_use_a_swept_prefix_while_unattached(self):
        for model, field_name in private_file_fields():
            condition = CONDITIONALLY_RETAINED.get(model._meta.label)
            if condition:
                instance = self._unsaved_probe(model)
                setattr(instance, condition, None)
                prefix = model._meta.get_field(field_name).generate_filename(instance, "probe.pdf").split("/", 1)[0]
                self.assertIn(prefix, SWEPT_STORAGE_PREFIXES)

    def test_the_receivers_are_connected_for_every_swept_field(self):
        connected = {lookup[0] for lookup, *_rest in post_delete.receivers}

        for model, field_name in swept_file_fields():
            with self.subTest(model=model._meta.label):
                self.assertIn(f"shared.storage.sweep:{model._meta.label}.{field_name}", connected)


class _StorageCase:
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.override = override_settings(PRIVATE_MEDIA_ROOT=self.root.name, MEDIA_ROOT=self.root.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(email="orphan-sweep@example.test", password="pw-12345678")

    def stored_files(self):
        return sorted(str(p.relative_to(self.root.name)) for p in Path(self.root.name).rglob("*") if p.is_file())

    def a_document(self):
        return Document.objects.create(
            uploaded_by=self.user,
            document_type=DocumentType.PAYSLIP,
            original_filename="payslip.pdf",
            mime_type="application/pdf",
            file=ContentFile(PDF, name="payslip.pdf"),
        )


class FilesFollowTheirRowsTest(_StorageCase, TransactionTestCase):
    def test_deleting_a_document_deletes_its_file(self):
        document = self.a_document()
        self.assertEqual(len(self.stored_files()), 1)

        document.delete()

        self.assertEqual(self.stored_files(), [])

    def test_a_rolled_back_delete_keeps_the_file(self):
        document = self.a_document()
        stored = self.stored_files()

        with transaction.atomic():
            document.delete()
            transaction.set_rollback(True)

        self.assertEqual(self.stored_files(), stored)
        self.assertEqual(Document.objects.count(), 1)

    def test_deleting_a_company_document_deletes_its_file(self):
        company = Company.objects.create(owner=self.user, name="Sweep Pty Ltd", acn="123456789")
        document = CompanyDocument.objects.create(
            company=company,
            document_type=CompanyDocument._meta.get_field("document_type").choices[0][0],
            file=ContentFile(PDF, name="asic.pdf"),
            file_size=len(PDF),
        )
        self.assertEqual(len(self.stored_files()), 1)

        document.delete()

        self.assertEqual(self.stored_files(), [])

    def test_classification_evidence_outlives_its_row(self):
        account = UserAccount.objects.create()
        classification = InvestorClassification.objects.create(
            user_account=account,
            category="product_value",
            declaration_accepted=True,
            declaration_text="Declared",
            evidence_file=ContentFile(PDF, name="evidence.pdf"),
            submitted_at=timezone.now(),
        )
        stored = self.stored_files()
        self.assertEqual(len(stored), 1)

        classification.delete()

        self.assertEqual(self.stored_files(), stored)


class OrphanSweepTest(_StorageCase, TestCase):
    def _orphan(self, name="documents/loose/stray.pdf"):
        private_storage().save(name, ContentFile(PDF))
        return name

    def test_a_file_no_row_references_is_swept_once_it_has_settled(self):
        self._orphan()

        found = orphaned_files(moment=timezone.now() + GRACE + timedelta(minutes=1))

        self.assertEqual(len(found), 1)

    def test_a_file_inside_the_grace_period_is_left_alone(self):
        self._orphan()

        self.assertEqual(orphaned_files(), [])

    def test_a_referenced_file_is_never_swept(self):
        document = self.a_document()

        found = orphaned_files(moment=timezone.now() + GRACE + timedelta(days=365))

        self.assertNotIn(document.file.name, found)
        self.assertEqual(found, [])

    def test_retained_prefixes_are_not_walked_at_all(self):
        private_storage().save("users/anything/investor-classifications/x/evidence.pdf", ContentFile(PDF))

        found = orphaned_files(moment=timezone.now() + GRACE + timedelta(days=365))

        self.assertEqual(found, [])

    def test_the_sweep_deletes_what_it_finds_and_reports_it(self):
        self._orphan()
        keep = self.a_document()

        result = sweep_orphaned_files(moment=timezone.now() + GRACE + timedelta(minutes=1))

        self.assertEqual((result["found"], result["deleted"], result["failed"]), (1, 1, 0))
        self.assertEqual(self.stored_files(), [keep.file.name])

    def test_a_dry_run_deletes_nothing(self):
        self._orphan()

        result = sweep_orphaned_files(moment=timezone.now() + GRACE + timedelta(minutes=1), dry_run=True)

        self.assertEqual((result["found"], result["deleted"]), (1, 0))
        self.assertEqual(len(self.stored_files()), 1)

    def test_a_storage_failure_is_counted_rather_than_raised(self):
        self._orphan()

        with patch.object(type(private_storage()), "delete", side_effect=OSError("bucket said no")):
            result = sweep_orphaned_files(moment=timezone.now() + GRACE + timedelta(minutes=1))

        self.assertEqual((result["found"], result["deleted"], result["failed"]), (1, 0, 1))

    def test_the_command_runs_and_reports(self):
        self._orphan()

        with patch("shared.management.commands.sweep_orphaned_files.sweep_orphaned_files") as sweep:
            sweep.return_value = {"found": 1, "deleted": 1, "failed": 0, "names": ["documents/loose/stray.pdf"]}
            call_command("sweep_orphaned_files", verbosity=0)

        sweep.assert_called_once_with(dry_run=False)
