from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment, AssetSnapshot
from assets.services.identity import quarantine_unknown_token
from assets.services.sync import SUPPORTED_ASSETS, AssetSyncService
from assets.tasks import sync_all_assets
from tokens.models import YieldToken


def midnight(moment):
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


class UpdatePriceTests(TestCase):
    def setUp(self):
        self.asset = Asset.objects.create(symbol="UPD", name="Update asset", asset_type="tokenized_security")
        self.today_midnight = midnight(timezone.now())

    def test_manual_prices_share_one_midnight_row_per_day(self):
        first = AssetSyncService.update_price(self.asset, Decimal("1.50"), source="manual", currency="USD")
        second = AssetSyncService.update_price(self.asset, Decimal("2.25"), source="coingecko", currency="AUD")

        self.assertEqual(AssetSnapshot.objects.filter(asset=self.asset).count(), 1)
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.source_timestamp, self.today_midnight)
        self.assertEqual(second.price, Decimal("2.25"))
        self.assertEqual(second.price_currency, "AUD")
        self.assertEqual(second.data_source, "coingecko")
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.current_price, Decimal("2.25"))
        self.assertEqual(self.asset.price_currency, "AUD")

    def test_existing_market_data_survives_a_manual_price(self):
        AssetSnapshot.objects.create(
            asset=self.asset,
            price=Decimal("1.00"),
            source_timestamp=self.today_midnight,
            data_source="nav_update",
            market_data={"custodian_report_ref": "ref-1"},
        )

        snapshot = AssetSyncService.update_price(self.asset, Decimal("1.10"))

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.price, Decimal("1.10"))
        self.assertEqual(snapshot.data_source, "manual")
        self.assertEqual(snapshot.market_data, {"custodian_report_ref": "ref-1"})

    def test_create_snapshot_false_only_updates_the_asset(self):
        self.assertIsNone(AssetSyncService.update_price(self.asset, Decimal("3"), create_snapshot=False))
        self.assertFalse(AssetSnapshot.objects.filter(asset=self.asset).exists())
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.current_price, Decimal("3"))

    def test_non_positive_price_is_rejected(self):
        with self.assertRaises(ValueError):
            AssetSyncService.update_price(self.asset, Decimal("0"))
        self.assertFalse(AssetSnapshot.objects.filter(asset=self.asset).exists())


class EnsureSupportedAssetsTests(TestCase):
    def test_upserts_every_supported_asset_with_its_deployment(self):
        AssetSyncService.ensure_supported_assets()
        AssetSyncService.ensure_supported_assets()

        self.assertEqual(Asset.objects.filter(symbol__in=SUPPORTED_ASSETS).count(), len(SUPPORTED_ASSETS))
        eth = Asset.objects.get(symbol="ETH")
        self.assertEqual(
            (eth.name, eth.asset_type, eth.decimals, eth.is_verified), ("Ethereum", "native_crypto", 18, True)
        )
        self.assertEqual(
            list(eth.chain_deployments.values_list("chain", "contract_address", "is_active")),
            [("ethereum", None, True)],
        )
        self.assertEqual(Asset.objects.native_for_chain("ethereum"), eth)

    def test_keeps_an_admin_deactivation_and_a_hand_entered_contract(self):
        usdc = Asset.objects.create(symbol="USDC", name="old", asset_type="erc20_token", is_active=False)
        AssetChainDeployment.objects.create(
            asset=usdc, chain="ethereum", contract_address="0x" + "c" * 40, is_active=False
        )

        AssetSyncService.ensure_supported_assets()

        usdc.refresh_from_db()
        self.assertEqual(
            (usdc.name, usdc.asset_type, usdc.is_active, usdc.is_verified), ("USD Coin", "stablecoin", False, True)
        )
        deployment = usdc.chain_deployments.get(chain="ethereum")
        self.assertEqual(
            (deployment.contract_address, deployment.decimals, deployment.is_active), ("0x" + "c" * 40, 6, True)
        )


class SyncCurrentPricesTests(TestCase):
    def setUp(self):
        AssetSyncService.ensure_supported_assets()
        Asset.objects.create(symbol="AAPL.t", name="Apple", asset_type="tokenized_security")
        YieldToken.objects.create(
            name="AUSG", symbol="AUSG", contract_address="0x" + "d" * 40, nav_per_token=Decimal("1.02")
        )
        self.client_mock = MagicMock()
        self.client_mock.fetch_prices_by_symbols.return_value = {"BTC": {"price": "60000"}, "ETH": {"price": "3000.5"}}
        self.today_midnight = midnight(timezone.now())

    def price_rows(self):
        return {
            snapshot.asset.symbol: (snapshot.price, snapshot.data_source)
            for snapshot in AssetSnapshot.objects.select_related("asset").filter(source_timestamp=self.today_midnight)
        }

    def test_one_coingecko_call_then_one_midnight_row_per_priced_asset(self):
        with patch("assets.services.sync.CoinGeckoClient", return_value=self.client_mock) as client_class:
            result = AssetSyncService.sync_assets(today_only=True)

        client_class.assert_called_once_with()
        self.client_mock.fetch_prices_by_symbols.assert_called_once_with(
            {"BTC": "bitcoin", "ETH": "ethereum", "USDC": "usd-coin", "USDT": "tether"}
        )
        self.assertEqual(result, {"status": "success", "prices_updated": 4, "historical_snapshots": 0})
        self.assertEqual(
            self.price_rows(),
            {
                "BTC": (Decimal("60000"), "coingecko"),
                "ETH": (Decimal("3000.5"), "coingecko"),
                "AUDY": (Decimal("1.00"), "fixed_peg"),
                "AUSG": (Decimal("1.02"), "nav_update"),
            },
        )
        self.assertEqual(Asset.objects.get(symbol="ETH").current_price, Decimal("3000.5"))
        self.assertIsNone(Asset.objects.get(symbol="AAPL.t").current_price)

    def test_a_quarantined_row_under_a_coingecko_symbol_is_never_priced(self):
        doge = quarantine_unknown_token("ethereum", "0x" + "d0" * 20, "DOGE", 18)
        self.client_mock.fetch_prices_by_symbols.return_value["DOGE"] = {"price": "0.5"}

        with patch("assets.services.sync.CoinGeckoClient", return_value=self.client_mock):
            AssetSyncService.sync_assets(today_only=True)

        self.assertNotIn("DOGE", self.client_mock.fetch_prices_by_symbols.call_args.args[0])
        self.assertNotIn("DOGE", self.price_rows())
        doge.refresh_from_db()
        self.assertEqual((doge.symbol, doge.is_verified, doge.current_price), ("DOGE", False, None))

    def test_fixed_and_nav_prices_survive_a_coingecko_outage_and_inactive_assets_are_skipped(self):
        Asset.objects.filter(symbol="AUDY").update(is_active=False)
        self.client_mock.fetch_prices_by_symbols.side_effect = RuntimeError("down")

        with patch("assets.services.sync.CoinGeckoClient", return_value=self.client_mock):
            result = AssetSyncService.sync_assets(today_only=True)

        self.assertEqual(result["prices_updated"], 1)
        self.assertEqual(self.price_rows(), {"AUSG": (Decimal("1.02"), "nav_update")})

    def test_unexpected_failure_is_reported_not_raised(self):
        with patch("assets.services.sync.AssetSyncService._current_prices", side_effect=RuntimeError("boom")):
            self.assertEqual(AssetSyncService.sync_assets(), {"status": "error", "error": "RuntimeError: boom"})


class BackfillTests(TestCase):
    def setUp(self):
        AssetSyncService.ensure_supported_assets()
        self.btc = Asset.objects.get(symbol="BTC")
        self.now = timezone.now()
        self.day_before = midnight(self.now) - timedelta(days=2)
        self.yesterday = midnight(self.now) - timedelta(days=1)
        self.client_mock = MagicMock()
        self.client_mock.fetch_prices_by_symbols.return_value = {}

        self.client_mock.fetch_historical_prices_bulk.return_value = [
            {"timestamp": self.day_before + timedelta(hours=12), "price": Decimal("1")},
            {"timestamp": self.yesterday + timedelta(hours=12), "price": Decimal("2")},
            {"timestamp": self.yesterday + timedelta(hours=13), "price": Decimal("3")},
        ]

    def test_only_missing_midnights_are_created_from_one_history_call_per_asset(self):
        AssetSnapshot.objects.create(
            asset=self.btc,
            price=Decimal("9"),
            source_timestamp=midnight(self.now - timedelta(days=2)),
            data_source="manual",
        )

        with patch("assets.services.sync.CoinGeckoClient", return_value=self.client_mock), patch(
            "assets.services.sync.time.sleep"
        ):
            result = AssetSyncService.sync_assets(backfill_days=3)

        self.assertEqual(result["historical_snapshots"], 7)
        self.assertEqual(self.client_mock.fetch_historical_prices_bulk.call_count, 4)
        rows = AssetSnapshot.objects.filter(asset=self.btc).order_by("source_timestamp")
        self.assertEqual(
            [(row.price, row.data_source) for row in rows],
            [(Decimal("9"), "manual"), (Decimal("3"), "coingecko_historical")],
        )

    def test_well_covered_assets_are_not_fetched_again(self):
        for offset in range(3):
            AssetSnapshot.objects.create(
                asset=self.btc,
                price=Decimal("1"),
                source_timestamp=midnight(self.now - timedelta(days=offset)),
                data_source="x",
            )
        with patch("assets.services.sync.CoinGeckoClient", return_value=self.client_mock), patch(
            "assets.services.sync.time.sleep"
        ):
            AssetSyncService._backfill_historical_prices(days=3)

        self.assertEqual(
            [call.args[0] for call in self.client_mock.fetch_historical_prices_bulk.call_args_list],
            ["ethereum", "usd-coin", "tether"],
        )


class SyncTaskTests(TestCase):
    def test_task_creates_missing_supported_assets_once_then_syncs_prices_only(self):
        with patch("assets.tasks.sync.AssetSyncService") as service:
            service.sync_assets.return_value = {"status": "success"}
            self.assertEqual(sync_all_assets(timestamp=0), {"status": "success"})
            self.assertEqual(service.ensure_supported_assets.call_count, 1)
            service.sync_assets.assert_called_once_with(today_only=True)

            AssetSyncService.ensure_supported_assets()
            sync_all_assets(timestamp=0)
            self.assertEqual(service.ensure_supported_assets.call_count, 1)


class AssetSyncCommandTests(TestCase):
    def test_seed_only_upserts_the_supported_assets_without_touching_the_network(self):
        with patch.object(AssetSyncService, "sync_assets") as sync_assets:
            call_command("asset_sync", "--seed-only")
            call_command("asset_sync", "--seed-only")

        sync_assets.assert_not_called()
        self.assertEqual(
            Asset.objects.filter(symbol__in=SUPPORTED_ASSETS, is_verified=True).count(), len(SUPPORTED_ASSETS)
        )
