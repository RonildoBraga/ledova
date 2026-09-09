from unittest.mock import patch

from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from wallets.constants import (
    WALLET_VERIFICATION_STATUS_PENDING,
    WALLET_VERIFICATION_STATUS_VERIFIED,
)
from wallets.exceptions import VerificationChallengeNotFoundException


class WalletVerificationTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("owner")
        self.wallet = self.tenant.spare_wallet
        self.client.force_authenticate(self.tenant.user)

    def test_request_verification_persists_the_challenge_it_returns(self):
        response = self.client.post(f"/api/wallets/{self.wallet.uuid}/request-verification/")

        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertTrue(self.wallet.verification_challenge)
        self.assertEqual(response.json()["challenge"], self.wallet.verification_challenge)
        self.assertEqual(self.wallet.verification_status, WALLET_VERIFICATION_STATUS_PENDING)

    @patch("wallets.tasks.sync_wallet")
    @patch("wallets.services.verification.verify_wallet_signature", return_value=True)
    def test_valid_signature_verifies_wallet_and_enqueues_one_sync(self, verify_signature, sync_task):
        issued = self.client.post(f"/api/wallets/{self.wallet.uuid}/request-verification/")
        self.assertEqual(issued.status_code, 200)

        response = self.client.post(
            f"/api/wallets/{self.wallet.uuid}/verify-signature/", {"signature": "0x01"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verificationStatus"], WALLET_VERIFICATION_STATUS_VERIFIED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.verification_status, WALLET_VERIFICATION_STATUS_VERIFIED)
        self.assertEqual(self.wallet.verification_signature, "0x01")
        self.assertIsNotNone(self.wallet.verified_at)
        verify_signature.assert_called_once_with(self.wallet.address, issued.json()["challenge"], "0x01", "ETHEREUM")
        sync_task.defer.assert_called_once_with(wallet_uuid=str(self.wallet.uuid))

    @patch("wallets.tasks.sync_wallet")
    @patch("wallets.services.verification.verify_wallet_signature", return_value=True)
    def test_the_same_challenge_and_signature_cannot_be_replayed(self, verify_signature, sync_task):
        issued = self.client.post(f"/api/wallets/{self.wallet.uuid}/request-verification/")
        self.assertEqual(issued.status_code, 200)
        first = self.client.post(
            f"/api/wallets/{self.wallet.uuid}/verify-signature/", {"signature": "0x01"}, format="json"
        )
        self.assertEqual(first.status_code, 200)

        replay = self.client.post(
            f"/api/wallets/{self.wallet.uuid}/verify-signature/", {"signature": "0x01"}, format="json"
        )

        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.json()["detail"], VerificationChallengeNotFoundException.default_detail)
        self.wallet.refresh_from_db()
        self.assertIsNone(self.wallet.verification_challenge)
        self.assertEqual(verify_signature.call_count, 1)
        self.assertEqual(sync_task.defer.call_count, 1)
