from unittest.mock import ANY, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from integrations.kyc.base import NormalizedVerificationResult
from shared.models import Country
from users.models import Notification, UserAccount, UserProfile
from users.services.identity import IdentityVerificationService
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
        self.push_task.defer.side_effect = run_task  # run the deferred job inline so the row it writes is visible
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
