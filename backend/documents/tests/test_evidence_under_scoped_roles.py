from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from documents.models import Document, DocumentRead
from documents.tasks.retention import purge_document_evidence
from documents.tests.test_supporting_evidence import STORAGES
from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant


@override_settings(STORAGES=STORAGES)
class ScopedSupportingEvidenceTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        with use_operator():
            self.owner = make_tenant("scoped-payslip-owner")
            self.other = make_tenant("scoped-payslip-other")

    def test_the_app_can_attach_only_its_own_document_to_its_own_claim(self):
        self.signed_in_as(self.owner.user)
        url = f"/api/v1/documents/{self.owner.document.pk}/attach/"
        refused = self.client.post(url, {"classification": str(self.other.investor_classification.pk)}, format="json")
        self.assertEqual(refused.status_code, 404)
        accepted = self.client.post(url, {"classification": str(self.owner.investor_classification.pk)}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.content)
        with use_operator():
            self.owner.document.refresh_from_db()
            self.assertEqual(self.owner.document.classification_id, self.owner.investor_classification.pk)
        self.signed_in_as(self.other.user)
        self.assertEqual(self.client.get(f"/api/v1/documents/{self.owner.document.pk}/").status_code, 404)

    def test_operations_read_and_audit_run_on_the_operator_connection(self):
        with use_operator():
            reviewer = get_user_model().objects.create_user(
                email="scoped-doc-reviewer@example.test",
                password="pw-12345678",
                is_staff=True,
                is_active=True,
                is_email_verified=True,
            )
            reviewer.user_permissions.add(
                Permission.objects.get(content_type__app_label="documents", codename="view_document")
            )
        self.client.force_login(reviewer)
        response = self.client.get(reverse("admin:documents_document_file", args=[self.owner.document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b"".join(response.streaming_content))
        with use_operator():
            self.assertTrue(
                DocumentRead.objects.filter(actor_id=reviewer.pk, document_uuid=self.owner.document.pk).exists()
            )
            self.assertEqual(Document.objects.filter(pk=self.owner.document.pk).count(), 1)

    def test_losing_claim_membership_hides_the_linked_document_without_a_broken_join(self):
        self.signed_in_as(self.owner.user)
        url = f"/api/v1/documents/{self.owner.document.pk}/"
        response = self.client.post(
            url + "attach/", {"classification": str(self.owner.investor_classification.pk)}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        with use_operator():
            self.owner.account.user_profiles.remove(self.owner.profile)
        for suffix in ("", "file/"):
            self.assertEqual(self.client.get(url + suffix).status_code, 404)

    @override_settings(UNATTACHED_DOCUMENT_RETENTION_DAYS=1)
    def test_the_periodic_retention_sweep_uses_operator_scope_across_uploaders(self):
        ids = [self.owner.document.pk, self.other.document.pk]
        with use_operator():
            Document.objects.filter(pk__in=ids).update(created_at=timezone.now() - timedelta(days=2))
        self.signed_in_as(self.owner.user)
        self.assertEqual(purge_document_evidence(), {"purged": 2, "failed": 0})
        with use_operator():
            self.assertEqual(Document.objects.filter(pk__in=ids, purged_at__isnull=False).count(), 2)
