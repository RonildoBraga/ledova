from decimal import Decimal

from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from shared.tests.tenants import make_tenant
from wallets.models import Holding, Wallet

CLIENT_KEYS = ("nativeBalance", "nativeMarketValue", "marketValue")


class WalletReadContractTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("reader")
        self.client.force_authenticate(self.tenant.user)
        self.eth = Asset.objects.create(
            symbol="ETH", name="Ether", asset_type="native_crypto", is_verified=True, current_price=Decimal("3000")
        )
        AssetChainDeployment.objects.create(asset=self.eth, chain="base")
        Holding.objects.create(wallet=self.tenant.wallet, asset=self.eth, quantity=Decimal("0.5"))

    def test_list_reports_string_balances_from_holdings_without_per_row_queries(self):
        Wallet.objects.create(user_account=self.tenant.account, address="0x" + "9" * 40, chain="ethereum")

        with self.assertNumQueries(2):
            response = self.client.get("/api/wallets/")

        self.assertEqual(response.status_code, 200)
        rows = {row["uuid"]: row for row in response.json()["results"]}
        self.assertEqual(len(rows), 3)
        wallet = rows[str(self.tenant.wallet.uuid)]
        self.assertEqual(wallet["nativeBalance"], "0.500000000000000000")
        self.assertEqual(wallet["nativeMarketValue"], "1500.000000000000000000")

        self.assertEqual(wallet["marketValue"], "1510.000000000000000000")
        for key in CLIENT_KEYS:
            self.assertEqual(rows[str(self.tenant.spare_wallet.uuid)][key], "0.000000000000000000")

    def test_create_and_update_responses_carry_the_balance_keys(self):
        created = self.client.post(
            "/api/wallets/",
            {"userAccount": str(self.tenant.account.uuid), "address": "0x" + "8" * 40, "chain": "ethereum"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual([created.json()[key] for key in CLIENT_KEYS], ["0.000000000000000000"] * 3)

        updated = self.client.patch(f"/api/wallets/{self.tenant.wallet.uuid}/", {"name": "Main"}, format="json")
        self.assertEqual(updated.status_code, 200)
        body = updated.json()
        self.assertEqual(body["name"], "Main")
        self.assertEqual(body["nativeBalance"], "0.500000000000000000")
        self.assertEqual(body["marketValue"], "1510.000000000000000000")

    def test_wallet_model_no_longer_computes_balances_in_python(self):
        for name in ("native_balance", "native_market_value", "market_value"):
            self.assertFalse(hasattr(Wallet, name), name)
