from unittest.mock import patch

from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from wallets.constants import (
    WALLET_VERIFICATION_STATUS_PENDING,
    WALLET_VERIFICATION_STATUS_VERIFIED,
)
from wallets.models import Wallet


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

    @patch("wallets.views.wallet.sync_wallet")
    @patch("wallets.views.wallet.verify_wallet_signature", return_value=True)
    def test_valid_signature_verifies_wallet_and_enqueues_one_sync(self, verify_signature, sync_task):
        Wallet.objects.filter(pk=self.wallet.pk).update(verification_challenge="challenge")

        response = self.client.post(
            f"/api/wallets/{self.wallet.uuid}/verify-signature/", {"signature": "0x01"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verificationStatus"], WALLET_VERIFICATION_STATUS_VERIFIED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.verification_status, WALLET_VERIFICATION_STATUS_VERIFIED)
        self.assertEqual(self.wallet.verification_signature, "0x01")
        self.assertIsNotNone(self.wallet.verified_at)
        verify_signature.assert_called_once_with(self.wallet.address, "challenge", "0x01", "ETHEREUM")
        sync_task.defer.assert_called_once_with(wallet_uuid=str(self.wallet.uuid))
