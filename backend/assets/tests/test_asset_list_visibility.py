from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from shared.tests.tenants import make_tenant
from users.models import FavouriteAsset
from wallets.models import Holding

User = get_user_model()
SHARE = "0x" + "5e" * 20


class AssetListExcludesTokenizedSecuritiesTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("issuer")
        self.outsider = make_tenant("outsider")
        self.stablecoin = Asset.objects.create(
            symbol="USDC", name="USD Coin", asset_type="stablecoin", decimals=6, is_verified=True
        )
        AssetChainDeployment.objects.create(
            asset=self.stablecoin, chain="base", contract_address="0x" + "1" * 40, decimals=6
        )
        self.share = Asset.objects.create(
            symbol="ORD", name="Issuer Ordinary", asset_type="tokenized_security", decimals=0, is_verified=True
        )
        AssetChainDeployment.objects.create(asset=self.share, chain="base", contract_address=SHARE, decimals=0)
        self.client.force_authenticate(self.outsider.user)

    def _symbols(self, params=None):
        response = self.client.get("/api/assets/", params or {})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        return [row["symbol"] for row in payload.get("results", payload)]

    def test_a_share_class_never_reaches_another_investors_asset_list(self):
        symbols = self._symbols()

        self.assertIn("USDC", symbols)
        self.assertNotIn("ORD", symbols)
        self.assertNotIn("TENANT", symbols)

    def test_the_chain_filter_and_the_type_filter_cannot_reveal_it_either(self):
        self.assertNotIn("ORD", self._symbols({"chain": "base"}))
        self.assertNotIn("ORD", self._symbols({"asset_type": "tokenized_security"}))
        self.assertNotIn("ORD", self._symbols({"search": "Ordinary"}))

    def test_the_detail_and_snapshot_routes_are_closed_too(self):
        self.assertEqual(self.client.get(f"/api/assets/{self.share.uuid}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/assets/{self.share.uuid}/snapshots/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/assets/{self.stablecoin.uuid}/").status_code, 200)

    def test_the_holder_still_sees_the_share_holding_on_the_wallet_route(self):
        Holding.objects.create(wallet=self.tenant.wallet, asset=self.share, quantity=Decimal("250"))
        self.client.force_authenticate(self.tenant.user)

        response = self.client.get(f"/api/wallets/{self.tenant.wallet.uuid}/holdings/")

        self.assertEqual(response.status_code, 200)
        rows = {row["assetSymbol"]: row for row in response.json()}
        self.assertEqual(rows["ORD"]["quantity"], "250.000000000000000000")
        self.assertIsNone(rows["ORD"]["marketValue"])

    def test_the_directory_shaped_token_listing_is_unaffected(self):
        self.client.force_authenticate(self.tenant.user)

        response = self.client.get("/api/v1/trading/tokens/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get("results", payload)
        self.assertIn("DEP", [row["symbol"] for row in rows])

    def test_a_favourite_on_a_share_asset_is_still_readable_by_its_owner(self):
        favourite = FavouriteAsset.objects.create(user_account=self.tenant.account, asset=self.share)
        self.client.force_authenticate(self.tenant.user)

        response = self.client.get(f"/api/favourite-assets/{favourite.uuid}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["asset"]["symbol"], "ORD")
