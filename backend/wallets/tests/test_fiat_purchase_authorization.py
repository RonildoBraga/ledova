from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


class FiatPurchaseAuthorizationTest(APITestCase):
    def make_tenant(self, label):
        user = User.objects.create_user(email=f"{label}@fiat.example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create(account_number=f"FIAT-{label.upper()}")
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address="0x" + ("a" if label == "alice" else "b") * 40,
            chain="ethereum",
        )
        return user, profile, account, wallet

    def setUp(self):
        self.alice, self.alice_profile, self.alice_account, self.alice_wallet = self.make_tenant("alice")
        self.bob, self.bob_profile, self.bob_account, self.bob_wallet = self.make_tenant("bob")
        self.client.force_authenticate(self.alice)

    def test_widget_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(
            "/api/fiat-purchases/transak-widget-url/",
            {"walletUuid": str(self.alice_wallet.uuid)},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    @patch("wallets.views.fiat_purchase.generate_transak_widget_url", return_value="https://widget.example.test")
    def test_widget_accepts_owned_wallet_and_masks_foreign_wallet_existence(self, generate_widget_url):
        action_url = "/api/fiat-purchases/transak-widget-url/"
        own_response = self.client.post(
            action_url,
            {
                "walletUuid": str(self.alice_wallet.uuid),
                "chain": "base",
                "email": "attacker@example.test",
                "disableWalletAddressForm": False,
                "productsAvailed": "SELL",
            },
            format="json",
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(own_response.json()["walletAddress"], self.alice_wallet.address)
        generate_widget_url.assert_called_once()
        self.assertEqual(generate_widget_url.call_args.kwargs["wallet_address"], self.alice_wallet.address)
        self.assertEqual(generate_widget_url.call_args.kwargs["chain"], self.alice_wallet.chain)
        self.assertEqual(generate_widget_url.call_args.kwargs["email"], self.alice.email)
        self.assertTrue(generate_widget_url.call_args.kwargs["disable_wallet_address_form"])
        self.assertEqual(generate_widget_url.call_args.kwargs["products_availed"], "BUY")

        foreign_response = self.client.post(
            action_url,
            {"walletUuid": str(self.bob_wallet.uuid)},
            format="json",
        )
        missing_response = self.client.post(
            action_url,
            {"walletUuid": str(uuid4())},
            format="json",
        )
        self.assertEqual(foreign_response.status_code, 404)
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(foreign_response.json(), missing_response.json())
        self.assertNotIn(self.bob_wallet.address, foreign_response.content.decode())
