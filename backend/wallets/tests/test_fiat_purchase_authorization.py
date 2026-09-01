"""Tenant authorization regressions for fiat purchase records and widget setup."""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import UserAccount, UserProfile
from wallets.models import FiatTransaction, Wallet

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

    @staticmethod
    def rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    @staticmethod
    def make_purchase(*, external_id, user, wallet):
        return FiatTransaction.objects.create(
            external_id=external_id,
            user=user,
            wallet=wallet,
            fiat_amount=Decimal("100.00"),
            fiat_currency="AUD",
            crypto_amount=Decimal("0.025"),
            crypto_currency="ETH",
            status="COMPLETED",
        )

    def setUp(self):
        self.alice, self.alice_profile, self.alice_account, self.alice_wallet = self.make_tenant("alice")
        self.bob, self.bob_profile, self.bob_account, self.bob_wallet = self.make_tenant("bob")
        self.alice_purchase = self.make_purchase(
            external_id="fiat-alice",
            user=self.alice,
            wallet=self.alice_wallet,
        )
        self.bob_purchase = self.make_purchase(
            external_id="fiat-bob",
            user=self.bob,
            wallet=self.bob_wallet,
        )
        self.inconsistent_purchase = self.make_purchase(
            external_id="fiat-inconsistent",
            user=self.alice,
            wallet=self.bob_wallet,
        )
        self.client.force_authenticate(self.alice)

    def test_list_and_detail_require_direct_user_and_live_wallet_visibility(self):
        list_response = self.client.get("/api/fiat-purchases/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            {row["uuid"] for row in self.rows(list_response)},
            {str(self.alice_purchase.uuid)},
        )

        own_response = self.client.get(f"/api/fiat-purchases/{self.alice_purchase.uuid}/")
        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(own_response.json()["walletAddress"], self.alice_wallet.address)
        self.assertEqual(own_response.json()["chain"], self.alice_wallet.chain)

        for hidden_purchase in (self.bob_purchase, self.inconsistent_purchase):
            with self.subTest(purchase=hidden_purchase.uuid):
                response = self.client.get(f"/api/fiat-purchases/{hidden_purchase.uuid}/")
                self.assertEqual(response.status_code, 404)

        foreign_response = self.client.get(f"/api/fiat-purchases/{self.bob_purchase.uuid}/")
        missing_response = self.client.get(f"/api/fiat-purchases/{uuid4()}/")
        self.assertEqual(foreign_response.status_code, 404)
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(foreign_response.json(), missing_response.json())

    def test_membership_removal_revokes_existing_purchase_visibility(self):
        self.alice_account.user_profiles.remove(self.alice_profile)

        list_response = self.client.get("/api/fiat-purchases/")
        detail_response = self.client.get(f"/api/fiat-purchases/{self.alice_purchase.uuid}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(self.rows(list_response), [])
        self.assertEqual(detail_response.status_code, 404)

    def test_provider_records_are_read_only_and_cannot_be_reassigned_or_deleted(self):
        collection_response = self.client.post(
            "/api/fiat-purchases/",
            {
                "externalId": "caller-created",
                "wallet": str(self.bob_wallet.uuid),
                "fiatAmount": "1.00",
                "cryptoCurrency": "ETH",
            },
            format="json",
        )
        self.assertEqual(collection_response.status_code, 405)

        detail_url = f"/api/fiat-purchases/{self.alice_purchase.uuid}/"
        for method, payload in (
            ("put", {"wallet": str(self.bob_wallet.uuid)}),
            ("patch", {"wallet": str(self.bob_wallet.uuid), "fiatAmount": "1.00"}),
            ("delete", None),
        ):
            with self.subTest(method=method):
                response = getattr(self.client, method)(detail_url, payload, format="json")
                self.assertEqual(response.status_code, 405)

        self.alice_purchase.refresh_from_db()
        self.assertEqual(self.alice_purchase.wallet, self.alice_wallet)
        self.assertEqual(self.alice_purchase.fiat_amount, Decimal("100.00"))
        self.assertTrue(FiatTransaction.objects.filter(pk=self.alice_purchase.pk).exists())

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
