from decimal import Decimal
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from assets.models import Asset, ExchangeRate
from assets.services.sync import AssetSyncService
from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.tenants import make_tenant
from tokens.models import YieldToken
from tokens.services.yield_token_service import YieldTokenService
from wallets.models import Holding, Wallet


class ValuationSourcesTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("valuation")
        self.wallet = Wallet.objects.create(user_account=self.tenant.account, address="0x" + "7" * 40, chain="base")
        AssetSyncService.ensure_supported_assets()
        self.client = APIClient()
        self.client.force_authenticate(self.tenant.user)

    def a_holding(self, symbol, quantity):
        return Holding.objects.create(
            wallet=self.wallet, asset=Asset.objects.get(symbol=symbol), quantity=Decimal(quantity)
        )

    def rate(self, value="2"):
        ExchangeRate.objects.update_or_create(
            base_currency="USD", target_currency="AUD", defaults={"rate": Decimal(value)}
        )

    def sync(self):
        provider = Mock()
        provider.fetch_prices_by_symbols.return_value = {"ETH": {"price": "10"}}
        with patch("assets.services.sync.CoinGeckoClient", return_value=provider):
            return AssetSyncService.sync_assets(today_only=True)

    def test_market_nav_and_aud_par_are_real_usd_values_in_the_holding_api_and_wallet_total(self):
        self.rate()
        YieldToken.objects.create(
            name="NAV asset", symbol="AUSG", contract_address="0x" + "d" * 40, nav_per_token="1.25"
        )
        self.assertEqual(self.sync()["status"], "success")
        market = self.a_holding("ETH", "2")
        nav = self.a_holding("AUSG", "4")
        par = self.a_holding("AUDY", "10")
        self.assertEqual((market.market_value, market.value_source), (Decimal("20"), "market"))
        self.assertEqual((nav.market_value, nav.value_source), (Decimal("5"), "nav"))
        self.assertEqual((par.market_value, par.value_source), (Decimal("5"), "par"))
        wallet = Wallet.objects.with_market_value().get(pk=self.wallet.pk)
        self.assertEqual(wallet.annotated_market_value, Decimal("30"))
        response = self.client.get(f"/api/wallets/{wallet.pk}/holdings/?include_asset=true")
        self.assertEqual(response.status_code, 200)
        sources = {row["assetSymbol"]: row["valueSource"] for row in response.json()}
        self.assertEqual(sources, {"ETH": "market", "AUSG": "nav", "AUDY": "par"})

    def test_par_without_an_exchange_rate_is_unpriced_instead_of_one_us_dollar(self):
        ExchangeRate.objects.all().delete()
        self.sync()
        par = self.a_holding("AUDY", "10")
        self.assertIsNone(par.market_value)
        self.assertEqual(par.value_source, "unpriced")
        self.assertEqual(Wallet.objects.with_market_value().get(pk=self.wallet.pk).annotated_market_value, 0)

    def test_a_nav_update_records_its_source_at_the_same_time_as_the_price(self):
        nav_token = YieldToken.objects.create(name="NAV asset", symbol="AUSG", contract_address="0x" + "d" * 40)
        service = YieldTokenService.__new__(YieldTokenService)
        service.update_nav(Decimal("1.25"), Decimal("500"), self.tenant.user, nav_token, update_on_chain=False)
        holding = self.a_holding("AUSG", "4")
        self.assertEqual((holding.market_value, holding.value_source), (Decimal("5"), "nav"))
        snapshot = holding.asset.snapshots.get()
        self.assertEqual((snapshot.data_source, snapshot.price), ("nav_update", Decimal("1.25")))
        self.assertEqual(snapshot.market_data["total_reserve_value"], "500")

    def test_a_legacy_quote_without_provenance_is_retained_but_excluded_from_valuations(self):
        asset = Asset.objects.get(symbol="ETH")
        Asset.objects.filter(pk=asset.pk).update(current_price=99, price_source=None)
        holding = self.a_holding("ETH", "2")
        self.assertEqual(holding.asset.current_price, 99)
        self.assertIsNone(holding.market_value)
        self.assertEqual(holding.value_source, "unpriced")
        self.assertEqual(Wallet.objects.with_market_value().get(pk=self.wallet.pk).annotated_market_value, 0)
        self.assertEqual(Wallet.objects.with_market_value().get(pk=self.wallet.pk).annotated_native_balance, 2)
        response = self.client.get(f"/api/wallets/{self.wallet.pk}/holdings/?include_asset=true")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()[0]["asset"]["currentPrice"])
        self.assertEqual(response.json()[0]["asset"]["valueSource"], "unpriced")

    def test_a_manual_aud_quote_is_converted_before_it_can_enter_a_usd_total(self):
        self.rate()
        asset = Asset.objects.get(symbol="ETH")
        AssetSyncService.update_price(asset, Decimal("3"), currency="AUD")
        holding = self.a_holding("ETH", "2")
        self.assertEqual((holding.market_value, holding.value_source), (Decimal("3"), "market"))
        self.assertEqual(holding.asset.price_currency, "USD")

    def test_an_unconvertible_quote_leaves_the_prior_valuation_unchanged(self):
        asset = Asset.objects.get(symbol="ETH")
        AssetSyncService.update_price(asset, Decimal("7"))
        with self.assertRaisesRegex(ValueError, "No positive USD/EUR exchange rate"):
            AssetSyncService.update_price(asset, Decimal("3"), currency="EUR")
        asset.refresh_from_db()
        self.assertEqual((asset.valuation_price, asset.value_source), (Decimal("7"), "market"))


modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("assets" in modules and modules["assets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class PriceProvenanceMigrationTest(TransactionTestCase):
    def test_existing_quotes_are_preserved_without_guessing_their_source(self):
        self.addCleanup(restore_every_migration)
        historical = migrate_to([("assets", "0012_audy_base_deployment")]).get_model("assets", "Asset")
        row = historical.objects.create(symbol="OLD-QUOTE", name="Old quote", asset_type="erc20_token", current_price=7)
        restore_every_migration()
        restored = Asset.objects.get(pk=row.pk)
        self.assertEqual(restored.current_price, 7)
        self.assertIsNone(restored.price_source)
        self.assertEqual(restored.value_source, "unpriced")
        AssetSyncService.update_price(restored, Decimal("8"))
        self.assertEqual(restored.value_source, "market")
