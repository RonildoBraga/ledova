import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.fields.files import FieldFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from users.models import InvestorClassification, InvestorClassificationStatus
from users.services.investor_classification import purge_expired_evidence
from users.tasks.retention import purge_classification_evidence
from users.tests.factories import (
    attach_evidence,
    make_classification,
    make_investor,
    rejected_classification,
    revoked_classification,
    verified_classification,
)

User = get_user_model()

RETENTION_DAYS = 2557
ADMIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def age(classification, **fields):
    InvestorClassification.objects.filter(pk=classification.pk).update(**fields)
    classification.refresh_from_db()
    return classification


@override_settings(CLASSIFICATION_EVIDENCE_RETENTION_DAYS=RETENTION_DAYS)
class EvidencePurgeSweepTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_superuser(email="retention-staff@example.test", password="pw-12345678")
        self.long_past = timezone.now() - timedelta(days=RETENTION_DAYS + 1)
        self.just_inside = timezone.now() - timedelta(days=RETENTION_DAYS - 1)

    def _rejected(self, label, reviewed_at):
        _, account = make_investor(label)
        claim = attach_evidence(rejected_classification(account, self.reviewer))
        return age(claim, reviewed_at=reviewed_at)

    def test_a_rejected_claim_inside_the_window_keeps_its_evidence(self):
        claim = self._rejected("inside", self.just_inside)
        path = claim.evidence_file.path

        self.assertEqual(purge_expired_evidence(timezone.now(), 200), {"purged": 0, "failed": 0})
        claim.refresh_from_db()
        self.assertTrue(bool(claim.evidence_file))
        self.assertTrue(os.path.isfile(path))

    def test_a_rejected_claim_past_the_window_is_purged(self):
        claim = self._rejected("past", self.long_past)
        path = claim.evidence_file.path

        self.assertEqual(purge_expired_evidence(timezone.now(), 200), {"purged": 1, "failed": 0})
        claim.refresh_from_db()
        self.assertFalse(bool(claim.evidence_file))
        self.assertFalse(os.path.exists(path))

    def test_an_expired_claim_past_the_window_is_purged(self):
        _, account = make_investor("expired")
        claim = attach_evidence(verified_classification(account, self.reviewer, expires_at=self.long_past))

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 1)
        claim.refresh_from_db()
        self.assertFalse(bool(claim.evidence_file))

    def test_a_live_claim_is_never_purged_including_one_that_never_expires(self):
        _, dated = make_investor("live-dated")
        _, undated = make_investor("live-undated")
        attach_evidence(verified_classification(dated, self.reviewer, expires_at=timezone.now() + timedelta(days=1)))
        attach_evidence(verified_classification(undated, self.reviewer, expires_at=None))

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 0)

    def test_a_revoked_claim_runs_on_its_review_date_not_its_stale_expiry(self):
        _, account = make_investor("revoked")
        claim = attach_evidence(revoked_classification(account, self.reviewer, expires_at=self.long_past))
        age(claim, reviewed_at=self.just_inside)

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 0)

        age(claim, reviewed_at=self.long_past)
        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 1)

    def test_a_submitted_claim_is_never_purgeable(self):
        _, account = make_investor("open")
        attach_evidence(make_classification(account))

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 0)

    def test_a_rejected_claim_with_no_review_date_is_left_alone(self):
        claim = self._rejected("undated", self.long_past)
        age(claim, reviewed_at=None)

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 0)

    def test_the_row_and_its_outcome_survive_the_purge(self):
        claim = self._rejected("outcome", self.long_past)
        before = InvestorClassification.objects.values("status", "reviewed_by", "rejection_reason", "category").get(
            pk=claim.pk
        )

        purge_expired_evidence(timezone.now(), 200)

        claim.refresh_from_db()
        self.assertEqual(claim.status, InvestorClassificationStatus.REJECTED)
        self.assertEqual(
            InvestorClassification.objects.values("status", "reviewed_by", "rejection_reason", "category").get(
                pk=claim.pk
            ),
            before,
        )
        self.assertEqual(claim.evidence_mime_type, "application/pdf")
        self.assertEqual(claim.evidence_file_size, 12)

    def test_the_sweep_is_idempotent(self):
        self._rejected("twice", self.long_past)

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 1)
        self.assertEqual(purge_expired_evidence(timezone.now(), 200), {"purged": 0, "failed": 0})

    def test_a_blob_already_gone_from_storage_still_purges_the_row(self):
        claim = self._rejected("missing", self.long_past)
        os.remove(claim.evidence_file.path)

        self.assertEqual(purge_expired_evidence(timezone.now(), 200), {"purged": 1, "failed": 0})
        claim.refresh_from_db()
        self.assertFalse(bool(claim.evidence_file))

    def test_one_failing_row_does_not_abort_the_batch(self):
        self._rejected("fails", self.long_past)
        self._rejected("succeeds", self.long_past)

        with patch.object(FieldFile, "delete", side_effect=[OSError("gone"), None]):
            result = purge_expired_evidence(timezone.now(), 200)

        self.assertEqual(result, {"purged": 1, "failed": 1})

    def test_the_batch_limit_is_respected(self):
        self._rejected("batch-a", self.long_past)
        self._rejected("batch-b", self.long_past)

        self.assertEqual(purge_expired_evidence(timezone.now(), 1)["purged"], 1)

    def test_the_periodic_task_runs_the_sweep(self):
        self._rejected("task", self.long_past)

        self.assertEqual(purge_classification_evidence(), {"purged": 1, "failed": 0})

    @override_settings(CLASSIFICATION_EVIDENCE_RETENTION_DAYS=0)
    def test_a_retention_of_zero_purges_nothing(self):
        claim = self._rejected("never", self.long_past)

        self.assertEqual(purge_expired_evidence(timezone.now(), 200)["purged"], 0)
        claim.refresh_from_db()
        self.assertTrue(bool(claim.evidence_file))

    def test_the_queryset_and_the_property_agree_on_every_row(self):
        rows = []
        for index, clock in enumerate([self.long_past, self.just_inside, None]):
            _, rejected = make_investor(f"agree-rej-{index}")
            rows.append(age(attach_evidence(rejected_classification(rejected, self.reviewer)), reviewed_at=clock))
            _, verified = make_investor(f"agree-ver-{index}")
            rows.append(attach_evidence(verified_classification(verified, self.reviewer, expires_at=clock)))

        purgeable = set(InvestorClassification.objects.evidence_purgeable(timezone.now()).values_list("pk", flat=True))

        for row in rows:
            row.refresh_from_db()
            self.assertEqual(row.pk in purgeable, not row.evidence_retained, f"{row.status} clock={row.pk}")


@override_settings(CLASSIFICATION_EVIDENCE_RETENTION_DAYS=RETENTION_DAYS, STORAGES=ADMIN_STORAGES)
class EvidenceReadHorizonTest(APITestCase):

    def setUp(self):
        self.reviewer = User.objects.create_superuser(email="horizon-staff@example.test", password="pw-12345678")
        self.user, self.account = make_investor("horizon")
        self.claim = attach_evidence(rejected_classification(self.account, self.reviewer))
        age(self.claim, reviewed_at=timezone.now() - timedelta(days=RETENTION_DAYS + 1))
        self.url = f"/api/investor-classifications/{self.claim.uuid}/evidence/"

    def test_the_api_stops_serving_past_the_horizon_before_any_sweep_runs(self):
        self.assertTrue(os.path.isfile(self.claim.evidence_file.path))
        self.client.force_authenticate(self.user)

        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertTrue(os.path.isfile(self.claim.evidence_file.path))

    def test_the_admin_stops_serving_past_the_horizon_too(self):
        self.client.force_authenticate(None)
        self.client.force_login(self.reviewer)

        response = self.client.get(reverse("admin:users_investorclassification_evidence", args=[self.claim.uuid]))

        self.assertEqual(response.status_code, 404)

    def test_the_serializer_stops_advertising_the_url_past_the_horizon(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(f"/api/investor-classifications/{self.claim.uuid}/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["evidenceUrl"])

    def test_inside_the_horizon_the_bytes_still_stream(self):
        age(self.claim, reviewed_at=timezone.now() - timedelta(days=1))
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"evidence bytes")
