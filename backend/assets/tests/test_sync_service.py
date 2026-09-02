from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetSnapshot
from assets.services.sync import AssetSyncService


class UpdatePriceTests(TestCase):
    def setUp(self):
        self.asset = Asset.objects.create(symbol="UPD", name="Update asset", asset_type="tokenized_security")
        self.today_midnight = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

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
