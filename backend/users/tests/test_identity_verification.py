from unittest.mock import ANY, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from integrations.kyc.base import NormalizedVerificationResult
from shared.models import Country
from users.models import UserAccount, UserProfile
from users.services.identity import IdentityVerificationService

User = get_user_model()


class IdentityVerificationApprovalTest(TestCase):
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
