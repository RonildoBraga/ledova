from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from shared.tests.tenants import make_tenant
from users.models import UserAccount
from wallets.models import Holding, Wallet
from wallets.serializers.holding import HoldingSerializer

SHARED_ADDRESS = "0x" + "ab" * 20


class AssetDoesNotAnswerForAChainTest(TestCase):
    def test_the_model_no_longer_offers_an_arbitrary_chain_or_address(self):
        asset = Asset.objects.create(symbol="MLT", name="Multi", asset_type="stablecoin", decimals=6)

        self.assertFalse(hasattr(asset, "chain"))
        self.assertFalse(hasattr(asset, "contract_address"))

    def test_a_deployment_is_asked_for_a_chain_by_name(self):
        asset = Asset.objects.create(symbol="MLT", name="Multi", asset_type="stablecoin", decimals=6)
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address="0x" + "22" * 20, decimals=6)
        AssetChainDeployment.objects.create(
            asset=asset, chain="ethereum", contract_address="0x" + "11" * 20, decimals=6
        )

        self.assertEqual(asset.get_deployment_for_chain("ethereum").contract_address, "0x" + "11" * 20)
        self.assertEqual(asset.get_deployment_for_chain("base").contract_address, "0x" + "22" * 20)
        self.assertIsNone(asset.get_deployment_for_chain("bitcoin"))


class HoldingReportsItsWalletsChainTest(TestCase):
    def setUp(self):
        self.asset = Asset.objects.create(symbol="MLT", name="Multi", asset_type="stablecoin", decimals=6)
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="base", contract_address="0x" + "22" * 20, decimals=6
        )
        AssetChainDeployment.objects.create(
            asset=self.asset, chain="ethereum", contract_address="0x" + "11" * 20, decimals=6
        )

    def _holding(self, chain):
        wallet = Wallet.objects.create(
            user_account=UserAccount.objects.create(), address="0x" + chain[0] * 40, chain=chain
        )
        return Holding.objects.create(wallet=wallet, asset=self.asset, quantity=Decimal("1"))

    def test_a_holding_reports_the_chain_of_the_wallet_that_holds_it(self):
        self.assertEqual(HoldingSerializer(self._holding("ethereum")).data["chain"], "ethereum")
        self.assertEqual(HoldingSerializer(self._holding("base")).data["chain"], "base")

    def test_two_chains_holding_one_asset_are_told_apart(self):
        rows = [HoldingSerializer(self._holding(chain)).data for chain in ("ethereum", "base")]

        self.assertEqual(sorted(row["chain"] for row in rows), ["base", "ethereum"])
        self.assertEqual({row["assetSymbol"] if "assetSymbol" in row else row["asset_symbol"] for row in rows}, {"MLT"})


class HoldingsRouteCarriesTheChainTest(APITestCase):
    def test_the_holdings_action_labels_each_row_with_its_own_wallets_chain(self):
        tenant = make_tenant("chain-label")
        asset = Asset.objects.create(symbol="MLT", name="Multi", asset_type="stablecoin", decimals=6)
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address="0x" + "22" * 20, decimals=6)
        AssetChainDeployment.objects.create(
            asset=asset, chain="ethereum", contract_address="0x" + "11" * 20, decimals=6
        )
        Holding.objects.create(wallet=tenant.wallet, asset=asset, quantity=Decimal("2"))
        self.client.force_authenticate(tenant.user)

        response = self.client.get(f"/api/wallets/{tenant.wallet.uuid}/holdings/")

        self.assertEqual(response.status_code, 200)
        rows = response.json()
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        self.assertEqual({row["chain"] for row in rows}, {tenant.wallet.chain})
