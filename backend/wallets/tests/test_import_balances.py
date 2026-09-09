from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings
from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from wallets.models import Wallet

ADDRESS = "0x" + "a" * 40
OTHER_ADDRESS = "0x" + "b" * 40


class ImportBalancePreviewTest(APITestCase):
    def setUp(self):
        self.owner = make_tenant("preview-owner")
        self.foreign = make_tenant("preview-foreign")
        self.client.force_authenticate(self.owner.user)
        self.payload = {"userAccount": str(self.owner.account.pk), "chain": "base", "addresses": [ADDRESS]}

    def post_preview(self, **changes):
        return self.client.post("/api/wallets/batch-check-balances/", {**self.payload, **changes}, format="json")

    def test_an_unregistered_address_is_queried_on_the_explicit_network_without_writing_a_wallet(self):
        before = Wallet.objects.count()
        for chain, quantity in (("base", "5"), ("ethereum", "2")):
            with self.subTest(chain=chain), patch("wallets.services.balance.get_blockchain_client") as get_client:
                get_client.return_value.get_native_balance.return_value = Decimal(quantity)
                response = self.post_preview(chain=chain)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(
                    response.json(),
                    {"userAccount": str(self.owner.account.pk), "chain": chain, "balances": {ADDRESS: quantity}},
                )
                get_client.assert_called_once_with(chain)
                get_client.return_value.get_native_balance.assert_called_once_with(ADDRESS)
        self.assertEqual(Wallet.objects.count(), before)

    def test_foreign_phantom_and_removed_membership_accounts_never_reach_a_provider(self):
        self.owner.account.user_profiles.remove(self.owner.profile)
        bodies = []
        with patch("wallets.services.balance.get_blockchain_client") as provider:
            for account in (self.owner.account.pk, self.foreign.account.pk, uuid4()):
                response = self.post_preview(userAccount=str(account))
                self.assertEqual(response.status_code, 404, response.content)
                bodies.append(response.json())
        self.assertTrue(all(body == bodies[0] for body in bodies))
        provider.assert_not_called()

    def test_missing_scope_and_invalid_addresses_are_rejected_before_a_provider_call(self):
        invalid = [
            {key: value for key, value in self.payload.items() if key != omitted}
            for omitted in ("userAccount", "chain", "addresses")
        ]
        invalid.extend(
            {**self.payload, **change}
            for change in (
                {"addresses": []},
                {"addresses": [ADDRESS] * 21},
                {"addresses": ["bad"]},
                {"addresses": [None]},
                {"chain": "unknown"},
                {"chain": "bitcoin"},
            )
        )
        with patch("wallets.services.balance.get_blockchain_client") as provider:
            for payload in invalid:
                with self.subTest(payload=payload):
                    response = self.client.post("/api/wallets/batch-check-balances/", payload, format="json")
                    self.assertEqual(response.status_code, 400, response.content)
        provider.assert_not_called()

    def test_zero_remains_zero_but_an_unavailable_balance_is_null(self):
        with patch("wallets.services.balance.get_blockchain_client") as provider:
            provider.return_value.get_native_balance.side_effect = [
                Decimal("0"),
                RuntimeError("private provider failure"),
            ]
            response = self.post_preview(addresses=[ADDRESS, OTHER_ADDRESS])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["balances"], {ADDRESS: "0", OTHER_ADDRESS: None})
        self.assertTrue(response.json()["errors"])
        self.assertNotIn("private provider failure", response.content.decode())

    def test_provider_failure_and_invalid_numeric_balances_never_become_zero(self):
        for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), None):
            with self.subTest(value=value), patch("wallets.services.balance.get_blockchain_client") as provider:
                provider.return_value.get_native_balance.return_value = value
                response = self.post_preview()
                self.assertEqual(response.json()["balances"], {ADDRESS: None})
        with patch("wallets.services.balance.get_blockchain_client", side_effect=RuntimeError("unavailable")):
            response = self.post_preview()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["balances"], {ADDRESS: None})

    def test_repeated_addresses_are_queried_once(self):
        with patch("wallets.services.balance.get_blockchain_client") as provider:
            provider.return_value.get_native_balance.return_value = Decimal("1")
            response = self.post_preview(addresses=[ADDRESS, ADDRESS])
        self.assertEqual(response.status_code, 200, response.content)
        provider.return_value.get_native_balance.assert_called_once_with(ADDRESS)

    @override_settings(BITCOIN_NETWORK="test")
    def test_bitcoin_previews_use_the_bitcoin_provider_and_refuse_mainnet_addresses(self):
        address = "mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn"
        with patch("wallets.services.balance.get_blockchain_client") as provider:
            provider.return_value.get_native_balance.return_value = Decimal("0.00000001")
            response = self.post_preview(chain="bitcoin", addresses=[address])
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(Decimal(response.json()["balances"][address]), Decimal("0.00000001"))
            provider.assert_called_once_with("bitcoin")
            provider.reset_mock()
            response = self.post_preview(chain="bitcoin", addresses=["1BoatSLRHtKNngkdXEeobR76b53LETtpyT"])
            self.assertEqual(response.status_code, 400, response.content)
            provider.assert_not_called()
