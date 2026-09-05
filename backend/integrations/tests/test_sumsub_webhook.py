import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from users.models import UserAccount, UserProfile
from users.services.identity import IdentityVerificationService

User = get_user_model()

SECRET = "s3cret"


@override_settings(SUMSUB_WEBHOOK_SECRET=SECRET)
class SumSubWebhookTest(APITestCase):
    def setUp(self):
        user = User.objects.create_user(email="sumsub@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=user, kyc_provider="sumsub", sumsub_applicant_id="app-1")
        self.account = UserAccount.objects.create(account_number="SUMSUB-ACC", director=self.profile)
        self.account.user_profiles.add(self.profile)

    def post_event(self, event_type, applicant_id="app-1", **extra):
        # Mirrors the real SumSub webhook shape: every key is camelCase.
        payload = {
            "type": event_type,
            "applicantId": applicant_id,
            "externalUserId": str(self.profile.uuid),
            "correlationId": "req-1",
            "levelName": "basic-kyc-level",
            "createdAtMs": "2026-09-03 00:00:00.000",
            **extra,
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse("sumsub-webhook"), body, content_type="application/json", HTTP_X_PAYLOAD_DIGEST=signature
        )

    def test_reviewed_event_reads_sumsub_camel_case_keys_and_verifies(self):
        with patch.object(IdentityVerificationService, "_trigger_risk_assessment") as risk_assessment, patch(
            "users.tasks.notifications.send_push_notification"
        ) as push_task:
            response = self.post_event(
                "applicantReviewed", reviewStatus="completed", reviewResult={"reviewAnswer": "GREEN"}
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.profile.refresh_from_db()
        self.account.refresh_from_db()
        self.assertTrue(self.profile.is_id_verified)
        self.assertIsNotNone(self.profile.verified_at)
        self.assertEqual(self.profile.verification_status, "completed")
        self.assertEqual(self.profile.review_result, "GREEN")
        self.assertEqual(self.profile.sumsub_verification_status, "completed")
        self.assertEqual(self.account.account_status, "active")
        risk_assessment.assert_called_once()
        self.assertEqual(risk_assessment.call_args.args[0], self.account)
        self.assertEqual(push_task.defer.call_args.kwargs["title"], "Identity verified")

    def test_pending_event_updates_the_status_clients_display(self):
        response = self.post_event("applicantPending", reviewStatus="pending")

        self.assertEqual(response.status_code, 200, response.content)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.sumsub_verification_status, "pending")
        self.assertFalse(self.profile.is_id_verified)

    def test_created_and_on_hold_events_track_status(self):
        self.assertEqual(self.post_event("applicantCreated").status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.sumsub_verification_status, "init")

        self.assertEqual(self.post_event("applicantOnHold").status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.sumsub_verification_status, "onHold")

    def test_new_applicant_id_is_stored_from_the_camel_case_key(self):
        response = self.post_event("applicantPending", applicant_id="app-2")

        self.assertEqual(response.status_code, 200, response.content)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.sumsub_applicant_id, "app-2")

    def test_snake_case_ids_are_not_accepted(self):
        payload = {"type": "applicantPending", "applicant_id": "app-1", "external_user_id": str(self.profile.uuid)}
        body = json.dumps(payload).encode()
        signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("sumsub-webhook"), body, content_type="application/json", HTTP_X_PAYLOAD_DIGEST=signature
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Missing externalUserId"})

    def test_bad_signature_is_rejected(self):
        response = self.client.post(
            reverse("sumsub-webhook"), b"{}", content_type="application/json", HTTP_X_PAYLOAD_DIGEST="nope"
        )

        self.assertEqual(response.status_code, 400)
