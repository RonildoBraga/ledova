from unittest.mock import ANY, patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from compliance.services.risk_assessment import RiskAssessmentService
from integrations.kyc.base import NormalizedVerificationResult
from shared.models import Country
from users.models import Notification, UserAccount, UserProfile
from users.services.identity import REVIEW_OUTCOME_MESSAGES, IdentityVerificationService
from users.tasks.notifications import send_push_notification as run_task

User = get_user_model()
PUSH_TASK = "users.tasks.notifications.send_push_notification"


class IdentityVerificationApprovalTest(TestCase):
    def setUp(self):
        self.push_task = patch(PUSH_TASK).start()
        self.addCleanup(patch.stopall)

    def _profile_with_citizenship(self, code):
        user = User.objects.create_user(email=f"{code.lower()}@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(
            user=user, citizenship_country=Country.objects.create(name="Test", code=code)
        )
        account = UserAccount.objects.create(account_number=f"ACC-{code}")
        account.user_profiles.add(profile)
        return profile, account

    @staticmethod
    def _green():
        return NormalizedVerificationResult(verification_status="completed", review_result="GREEN", is_verified=True)

    def test_green_result_with_citizenship_activates_account(self):
        profile, account = self._profile_with_citizenship("AU")

        with patch.object(IdentityVerificationService, "_trigger_risk_assessment") as risk_assessment:
            self.assertTrue(IdentityVerificationService.update_status_from_normalized(profile, self._green()))

        profile.refresh_from_db()
        account.refresh_from_db()
        self.assertTrue(profile.is_id_verified)
        self.assertEqual(account.account_status, "active")
        self.assertIsNone(profile.sumsub_verification_status)
        risk_assessment.assert_called_once_with(account, ANY)

    def test_green_result_with_blacklisted_citizenship_rejects_account(self):
        profile, account = self._profile_with_citizenship("kp")

        with patch.object(IdentityVerificationService, "_trigger_risk_assessment") as risk_assessment:
            IdentityVerificationService.update_status_from_normalized(profile, self._green())

        account.refresh_from_db()
        self.assertEqual(account.account_status, "rejected")
        self.assertEqual(account.rejection_reason, "fatf_blacklist")
        risk_assessment.assert_not_called()

    def test_sumsub_profile_also_records_the_status_clients_display(self):
        profile, _ = self._profile_with_citizenship("NZ")
        profile.kyc_provider = "sumsub"
        profile.save(update_fields=["kyc_provider"])

        with patch.object(IdentityVerificationService, "_trigger_risk_assessment"):
            IdentityVerificationService.update_status_from_normalized(profile, self._green())

        profile.refresh_from_db()
        self.assertEqual(profile.sumsub_verification_status, "completed")
        self.assertEqual(profile.verification_status, "completed")

    def test_yellow_result_flags_a_retry(self):
        profile, _ = self._profile_with_citizenship("GB")
        yellow = NormalizedVerificationResult(
            verification_status="completed", review_result="YELLOW", is_verified=False
        )

        IdentityVerificationService.update_status_from_normalized(profile, yellow)

        profile.refresh_from_db()
        self.assertTrue(profile.needs_verification_retry)
        self.assertFalse(profile.is_id_verified)

    def test_a_changed_review_result_creates_one_general_notification(self):
        profile, _ = self._profile_with_citizenship("IE")
        self.push_task.defer.side_effect = run_task
        yellow = NormalizedVerificationResult(
            verification_status="completed", review_result="YELLOW", is_verified=False
        )

        with patch.object(IdentityVerificationService, "_trigger_risk_assessment"):
            IdentityVerificationService.update_status_from_normalized(profile, yellow)
            IdentityVerificationService.update_status_from_normalized(profile, yellow)
            IdentityVerificationService.update_status_from_normalized(profile, self._green())

        self.assertEqual(self.push_task.defer.call_count, 2)
        self.push_task.defer.assert_called_with(
            user_id=str(profile.user.pk),
            title="Identity verified",
            body="Your identity has been verified.",
            notification_type="general",
        )
        rows = Notification.objects.filter(user=profile.user, notification_type="general").order_by("created_at")
        self.assertEqual([row.title for row in rows], ["Verification needs attention", "Identity verified"])

    def test_outcome_bodies_never_tell_the_reader_to_open_the_app_from_inside_a_push(self):
        for result, (title, body) in REVIEW_OUTCOME_MESSAGES.items():
            with self.subTest(result=result):
                self.assertNotIn("open the app", body.lower())
                self.assertTrue(title and body)

    def test_a_failing_risk_assessment_keeps_the_verified_result_and_its_notification(self):
        profile, account = self._profile_with_citizenship("DE")

        def broken_assessment(**kwargs):
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO no_such_table (x) VALUES (1)")

        with patch.object(RiskAssessmentService, "calculate_and_create", side_effect=broken_assessment):
            with self.assertLogs("users.services.identity", level="ERROR") as logs:
                self.assertTrue(IdentityVerificationService.update_status_from_normalized(profile, self._green()))

        self.assertIn("Error triggering risk assessment", "\n".join(logs.output))
        profile.refresh_from_db()
        account.refresh_from_db()
        self.assertTrue(profile.is_id_verified)
        self.assertEqual(account.account_status, "active")
        self.push_task.defer.assert_called_once()

    def test_a_job_that_cannot_be_deferred_rolls_the_saved_result_back(self):
        profile, _ = self._profile_with_citizenship("PT")
        self.push_task.defer.side_effect = RuntimeError("queue down")
        yellow = NormalizedVerificationResult(
            verification_status="completed", review_result="YELLOW", is_verified=False
        )

        with self.assertRaises(RuntimeError):
            IdentityVerificationService.update_status_from_normalized(profile, yellow)

        profile.refresh_from_db()
        self.assertIsNone(profile.review_result)
        self.assertNotEqual(profile.verification_status, "completed")


class IdentityVerificationStatusEndpointTest(APITestCase):
    @override_settings(KYC_PROVIDER="")
    def test_a_blank_provider_is_a_503_that_names_no_setting(self):
        user = User.objects.create_user(email="unconfigured@example.test", password="pw-12345678")
        UserProfile.objects.create(user=user)
        self.client.force_authenticate(user)

        with self.assertLogs("shared.api.exceptions", level="ERROR") as logs:
            response = self.client.get("/api/users/identity-verification/status/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"error": "Service not configured", "detail": "This feature is not configured on this server."},
        )
        self.assertNotIn("KYC_PROVIDER", response.content.decode())
        self.assertIn("KYC_PROVIDER", "\n".join(logs.output))


class PopulateProfileTest(TestCase):
    def test_residence_country_is_created_with_its_iso_name(self):
        user = User.objects.create_user(email="resident@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=user)

        self.assertTrue(
            IdentityVerificationService.populate_profile(
                profile, {"fullName": "Res Ident", "address": None, "dateOfBirth": None, "residenceCountry": "AUS"}
            )
        )

        profile.refresh_from_db()
        self.assertEqual(profile.full_name, "Res Ident")
        self.assertEqual((profile.residence_country.code, profile.residence_country.name), ("AUS", "Australia"))
