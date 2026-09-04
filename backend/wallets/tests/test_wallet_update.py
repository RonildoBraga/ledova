"""Wallet edits lock the row in the view and keep the response keys the clients read."""

from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from wallets.models import Wallet


class WalletUpdateTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("alice")
        self.client.force_authenticate(self.tenant.user)
        self.url = f"/api/wallets/{self.tenant.wallet.uuid}/"

    def test_patch_returns_the_wallet_with_market_values(self):
        response = self.client.patch(self.url, {"name": "Renamed"}, format="json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["uuid"], body["name"], body["chain"]), (str(self.tenant.wallet.uuid), "Renamed", "base"))
        self.assertEqual(body["verificationStatus"], "VERIFIED")
        self.assertIn("marketValue", body)
        self.assertIn("nativeMarketValue", body)
        self.assertEqual(Wallet.objects.get(pk=self.tenant.wallet.pk).name, "Renamed")

    def test_verified_identity_cannot_change_through_put_or_patch(self):
        new_address = "0x" + "d" * 40
        put_payload = {"userAccount": str(self.tenant.account.uuid), "address": new_address, "chain": "base"}

        for method, payload in ((self.client.patch, {"address": new_address}), (self.client.put, put_payload)):
            response = method(self.url, payload, format="json")
            with self.subTest(method=method.__name__):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["address"], ["Verified wallet identity cannot be changed."])

        self.assertEqual(Wallet.objects.get(pk=self.tenant.wallet.pk).address, self.tenant.wallet.address)
