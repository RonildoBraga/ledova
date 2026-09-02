"""Every wallet route must be not-found for another tenant's wallet, before any side effect."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


class WalletActionScopingTest(APITestCase):
    def setUp(self):
        self.alice, self.alice_account, self.alice_wallet = self._tenant("alice", "a")
        self.bob, self.bob_account, self.bob_wallet = self._tenant("bob", "b")
        self.client.force_authenticate(self.alice)

    @staticmethod
    def _tenant(label, character):
        user = User.objects.create_user(email=f"{label}@wallet-actions.example.test", password="pw-12345678")
        account = UserAccount.objects.create(account_number=f"WALLET-ACT-{label.upper()}")
        account.user_profiles.add(UserProfile.objects.create(user=user))
        wallet = Wallet.objects.create(user_account=account, address="0x" + character * 40, chain="ethereum")
        return user, account, wallet

    @staticmethod
    def _routes(wallet):
        base = f"/api/wallets/{wallet.uuid}/"
        return [
            ("get", base, None),
            ("patch", base, {"name": "renamed"}),
            ("delete", base, None),
            ("post", base + "request-verification/", None),
            ("post", base + "verify-signature/", {"signature": "0xsig"}),
            ("post", base + "sync/", None),
            ("post", base + "sync-holdings/", None),
            ("get", base + "holdings/", None),
            ("get", base + "balances/", None),
            ("get", base + "transactions/", None),
            ("post", base + "prepare-transfer/", {"toAddress": "0x" + "c" * 40, "amountEth": "0.1"}),
            ("post", base + "broadcast-transfer/", {"signedTransaction": "0xdead"}),
        ]

    @patch("wallets.views.wallet.sync_wallet")
    @patch("wallets.views.wallet.WalletSyncService")
    @patch("wallets.views.wallet.TransferService")
    def test_foreign_wallet_routes_are_not_found_without_side_effects(self, transfer_service, sync_service, sync_task):
        for method, url, payload in self._routes(self.bob_wallet):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, 404)

        self.bob_wallet.refresh_from_db()
        self.assertFalse(self.bob_wallet.verification_challenge)
        self.assertEqual(Wallet.objects.filter(user_account=self.bob_account).count(), 1)
        sync_task.defer.assert_not_called()
        sync_service.sync_wallet.assert_not_called()
        transfer_service.prepare_transfer.assert_not_called()
        transfer_service.broadcast_transfer.assert_not_called()

    def test_own_wallet_routes_resolve(self):
        base = f"/api/wallets/{self.alice_wallet.uuid}/"
        self.assertEqual(self.client.get(base).status_code, 200)
        self.assertEqual(self.client.get(base + "holdings/").status_code, 200)
        self.assertEqual(self.client.get(base + "transactions/").status_code, 200)
        self.assertEqual(self.client.post(base + "request-verification/").status_code, 200)
        self.alice_wallet.refresh_from_db()
        self.assertTrue(self.alice_wallet.verification_challenge)

    def test_wallet_cannot_be_created_in_a_foreign_account(self):
        response = self.client.post(
            "/api/wallets/",
            {
                "userAccount": str(self.bob_account.uuid),
                "address": "0x" + "d" * 40,
                "chain": "ethereum",
                "custodyModel": "non_custodial",
                "walletType": "software",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Wallet.objects.filter(user_account=self.bob_account).count(), 1)
