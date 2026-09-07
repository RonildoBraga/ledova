import tempfile
from pathlib import Path

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db.models import ProtectedError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from users.admin.investor_classification import InvestorClassificationAdmin
from users.exceptions import InvalidClassificationTransitionException
from users.models import UserAccount, UserProfile
from users.models.investor_classification import (
    InvestorClassification,
    InvestorClassificationStatus,
)
from users.services import lifecycle

User = get_user_model()

PDF = b"%PDF-1.4 evidence"
DETAIL = "/api/investor-classifications/{}/"


class _EvidenceCase:
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.override = override_settings(PRIVATE_MEDIA_ROOT=self.root.name, MEDIA_ROOT=self.root.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.user = User.objects.create_user(email="claimant@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create()
        self.account.user_profiles.add(self.profile)

    def stored_files(self):
        return sorted(str(p.relative_to(self.root.name)) for p in Path(self.root.name).rglob("*") if p.is_file())

    def a_claim(self, status=InvestorClassificationStatus.SUBMITTED):
        return InvestorClassification.objects.create(
            user_account=self.account,
            category="product_value",
            status=status,
            declaration_accepted=True,
            declaration_text="Declared",
            declared_basis="Holdings above the threshold.",
            evidence_file=ContentFile(PDF, name="evidence.pdf"),
            evidence_file_size=len(PDF),
            evidence_mime_type="application/pdf",
            submitted_at=timezone.now(),
        )


class TheMemberWithdrawsRatherThanDeletesTest(_EvidenceCase, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.user)

    def test_deleting_a_submitted_claim_withdraws_it_and_keeps_the_evidence(self):
        claim = self.a_claim()
        stored = self.stored_files()

        response = self.client.delete(DETAIL.format(claim.uuid))

        self.assertEqual(response.status_code, 204)
        claim.refresh_from_db()
        self.assertEqual(claim.status, InvestorClassificationStatus.WITHDRAWN)
        self.assertEqual(InvestorClassification.objects.count(), 1)
        self.assertEqual(self.stored_files(), stored)
        self.assertTrue(claim.evidence_file)

    def test_a_claim_an_operator_has_ruled_on_is_out_of_the_members_reach(self):
        for ruled in (
            InvestorClassificationStatus.VERIFIED,
            InvestorClassificationStatus.REJECTED,
            InvestorClassificationStatus.REVOKED,
            InvestorClassificationStatus.WITHDRAWN,
        ):
            with self.subTest(status=ruled):
                claim = self.a_claim(status=ruled)

                response = self.client.delete(DETAIL.format(claim.uuid))

                self.assertEqual(response.status_code, 404)
                claim.refresh_from_db()
                self.assertEqual(claim.status, ruled)
                self.assertEqual(InvestorClassification.objects.filter(pk=claim.pk).count(), 1)

    def test_the_model_refuses_the_transition_even_when_the_route_scope_is_bypassed(self):
        for ruled in (
            InvestorClassificationStatus.VERIFIED,
            InvestorClassificationStatus.REJECTED,
            InvestorClassificationStatus.REVOKED,
            InvestorClassificationStatus.WITHDRAWN,
        ):
            with self.subTest(status=ruled):
                claim = self.a_claim(status=ruled)

                with self.assertRaises(InvalidClassificationTransitionException):
                    claim.withdraw()

                claim.refresh_from_db()
                self.assertEqual(claim.status, ruled)

    def test_withdrawing_unblocks_a_fresh_submission(self):
        claim = self.a_claim()

        self.client.delete(DETAIL.format(claim.uuid))
        replacement = self.client.post(
            "/api/investor-classifications/",
            {
                "user_account": str(self.account.uuid),
                "category": "product_value",
                "declaration_accepted": True,
                "declared_basis": "Corrected evidence.",
                "evidence_file": ContentFile(PDF, name="corrected.pdf"),
            },
            format="multipart",
        )

        self.assertEqual(replacement.status_code, 201, replacement.content)
        self.assertEqual(InvestorClassification.objects.count(), 2)


class NoOperatorPathHardDeletesTest(_EvidenceCase, TestCase):
    def test_the_admin_refuses_to_delete_a_classification(self):
        admin = InvestorClassificationAdmin(InvestorClassification, AdminSite())
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(email="root@example.test", password="pw-12345678")

        self.assertFalse(admin.has_delete_permission(request))
        self.assertFalse(admin.has_delete_permission(request, self.a_claim()))

    def test_deleting_the_account_is_refused_while_a_classification_hangs_from_it(self):
        claim = self.a_claim()

        with self.assertRaises(ProtectedError):
            self.account.delete()

        self.assertTrue(InvestorClassification.objects.filter(pk=claim.pk).exists())
        self.assertEqual(len(self.stored_files()), 1)

    def test_deleting_the_user_does_not_reach_the_classification(self):
        claim = self.a_claim()
        stored = self.stored_files()

        self.user.delete()

        self.assertTrue(InvestorClassification.objects.filter(pk=claim.pk).exists())
        self.assertEqual(self.stored_files(), stored)

    def test_account_deletion_leaves_the_claim_and_its_evidence_standing(self):
        claim = self.a_claim()
        stored = self.stored_files()

        lifecycle.delete_account(self.user)

        claim.refresh_from_db()
        self.assertEqual(claim.status, InvestorClassificationStatus.SUBMITTED)
        self.assertEqual(self.stored_files(), stored)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
