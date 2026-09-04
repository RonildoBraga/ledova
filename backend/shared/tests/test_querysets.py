from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetSnapshot
from shared.utils.querysets import sample_evenly


class SampleEvenlyTest(TestCase):
    def setUp(self):
        asset = Asset.objects.create(symbol="SMP", name="Sampled", asset_type="tokenized_security")
        base = timezone.make_aware(datetime(2026, 1, 1))
        for day in range(10):
            AssetSnapshot.objects.create(
                asset=asset, price=Decimal(day), source_timestamp=base + timedelta(days=day), data_source="t"
            )
        self.ascending = AssetSnapshot.objects.order_by("source_timestamp")

    def prices(self, queryset):
        return [int(row.price) for row in queryset]

    def test_keeps_first_and_last_rows_in_the_queryset_order(self):
        self.assertEqual(self.prices(sample_evenly(self.ascending, 4)), [0, 3, 6, 9])
        self.assertEqual(self.prices(sample_evenly(self.ascending.reverse(), "4")), [9, 6, 3, 0])
        self.assertEqual(self.prices(sample_evenly(self.ascending, 1)), [0])

    def test_invalid_or_large_max_points_return_every_row(self):
        for max_points in (None, "", "abc", 0, -2, 10, 50):
            with self.subTest(max_points=max_points):
                self.assertEqual(len(self.prices(sample_evenly(self.ascending, max_points))), 10)
