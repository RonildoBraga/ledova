from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from eth_account import Account
from eth_account.messages import encode_defunct
from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from wallets.constants import (
    WALLET_VERIFICATION_STATUS_PENDING,
    WALLET_VERIFICATION_STATUS_VERIFIED,
)
from wallets.models import Wallet

SIGNER = Account.from_key("0x" + "44" * 32)


class WalletChallengeExpiryTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("expiring-wallet")
        self.wallet = Wallet.objects.create(user_account=self.tenant.account, address=SIGNER.address, chain="base")
        self.client.force_authenticate(self.tenant.user)
        self.issued_at = timezone.now()
        deferred = patch("wallets.tasks.sync_wallet.defer")
        self.addCleanup(deferred.stop)
        self.deferred = deferred.start()

    def issue(self, when=None):
        with patch("wallets.services.verification.timezone.now", return_value=when or self.issued_at):
            response = self.client.post(f"/api/wallets/{self.wallet.uuid}/request-verification/")
        self.assertEqual(response.status_code, 200, response.content)
        message = response.json()["challenge"]
        signature = SIGNER.sign_message(encode_defunct(text=message)).signature.to_0x_hex()
        return message, signature

    def verify(self, signature, when):
        with patch("wallets.services.verification.timezone.now", return_value=when):
            return self.client.post(
                f"/api/wallets/{self.wallet.uuid}/verify-signature/", {"signature": signature}, format="json"
            )

    def test_a_real_signature_just_before_five_minutes_is_accepted_and_clears_the_challenge(self):
        _, signature = self.issue()
        response = self.verify(signature, self.issued_at + timedelta(minutes=5) - timedelta(microseconds=1))
        self.assertEqual(response.status_code, 200, response.content)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.verification_status, WALLET_VERIFICATION_STATUS_VERIFIED)
        self.assertIsNone(self.wallet.verification_challenge)
        self.assertIsNone(self.wallet.verification_challenge_issued_at)
        self.deferred.assert_called_once()

    def test_a_real_signature_at_or_after_five_minutes_is_refused(self):
        for age in (timedelta(minutes=5), timedelta(days=1)):
            with self.subTest(age=age):
                _, signature = self.issue()
                response = self.verify(signature, self.issued_at + age)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("expired", response.json()["detail"].lower())
                self.wallet.refresh_from_db()
                self.assertEqual(self.wallet.verification_status, WALLET_VERIFICATION_STATUS_PENDING)
                self.assertIsNone(self.wallet.verified_at)
        self.deferred.assert_not_called()

    def test_requesting_again_replaces_the_nonce_and_starts_a_new_window(self):
        old_message, old_signature = self.issue()
        later = self.issued_at + timedelta(minutes=10)
        message, signature = self.issue(later)
        self.assertNotEqual(message, old_message)
        self.assertEqual(self.verify(old_signature, later).status_code, 400)
        response = self.verify(signature, later + timedelta(seconds=20))
        self.assertEqual(response.status_code, 200, response.content)
        self.deferred.assert_called_once()

    def test_a_legacy_challenge_without_an_issue_time_requires_a_new_challenge(self):
        _, signature = self.issue()
        Wallet.objects.filter(pk=self.wallet.pk).update(verification_challenge_issued_at=None)
        response = self.verify(signature, self.issued_at)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("new", response.json()["detail"].lower())
        self.deferred.assert_not_called()

    def test_a_future_issue_time_cannot_extend_the_window(self):
        _, signature = self.issue()
        Wallet.objects.filter(pk=self.wallet.pk).update(
            verification_challenge_issued_at=self.issued_at + timedelta(seconds=1)
        )
        response = self.verify(signature, self.issued_at)
        self.assertEqual(response.status_code, 400, response.content)
        self.deferred.assert_not_called()

    def test_a_consumed_real_signature_cannot_be_used_again(self):
        _, signature = self.issue()
        self.assertEqual(self.verify(signature, self.issued_at).status_code, 200)
        replay = self.verify(signature, self.issued_at + timedelta(seconds=1))
        self.assertEqual(replay.status_code, 400, replay.content)
        self.deferred.assert_called_once()

    def test_the_issue_time_matches_the_timestamp_the_owner_signs(self):
        message, _ = self.issue()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.verification_challenge_issued_at, self.issued_at)
        self.assertIn(f"Timestamp: {int(self.issued_at.timestamp())}", message)
