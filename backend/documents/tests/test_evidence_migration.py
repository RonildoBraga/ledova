from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TransactionTestCase

from documents.models import Document
from shared.tests.schema import migrate_to, restore_every_migration

modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("documents" in modules and modules["documents"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class SupportingEvidenceMigrationTest(TransactionTestCase):
    def test_existing_uploads_remain_unattached_and_operations_permissions_are_seeded_without_members(self):
        self.addCleanup(restore_every_migration)
        historical = migrate_to([("documents", "0002_document_private_storage")])
        Group.objects.filter(name="Document operations").delete()
        user = get_user_model().objects.create_user(email="old-payslip@example.test", password="pw-12345678")
        old_document = historical.get_model("documents", "Document").objects.create(
            uploaded_by_id=user.pk, original_filename="old.pdf", file="documents/old/old.pdf", document_type="payslip"
        )
        restore_every_migration()
        document = Document.objects.get(pk=old_document.pk)
        self.assertIsNone(document.classification_id)
        self.assertIsNone(document.purged_at)
        self.assertEqual(document.file.name, "documents/old/old.pdf")
        group = Group.objects.get(name="Document operations")
        self.assertEqual(
            set(group.permissions.values_list("codename", flat=True)),
            {"view_document", "view_documentextraction", "view_investorclassification"},
        )
        self.assertEqual(group.user_set.count(), 0)
