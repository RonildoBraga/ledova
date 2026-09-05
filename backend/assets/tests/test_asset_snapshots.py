from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment, AssetSnapshot
from users.models import UserProfile

User = get_user_model()


class AssetSnapshotsEndpointTest(APITestCase):
    def setUp(self):
        user = User.objects.create_user(email="snapshots@example.test", password="pw-12345678")
        UserProfile.objects.create(user=user)
        self.asset = Asset.objects.create(
            symbol="SNAP", name="Snapshot asset", asset_type="tokenized_security", is_verified=True
        )
        AssetChainDeployment.objects.create(asset=self.asset, chain="ethereum")
        base = timezone.make_aware(datetime(2026, 9, 1, 12, 0, 0))
        self.timestamps = [base + timedelta(days=offset) for offset in range(3)]
        for index, timestamp in enumerate(self.timestamps):
            AssetSnapshot.objects.create(
                asset=self.asset, price=index + 1, source_timestamp=timestamp, data_source="manual"
            )
        self.url = f"/api/assets/{self.asset.uuid}/snapshots/"
        self.client.force_authenticate(user)

    def _prices(self, params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return [row["price"] for row in response.json()]

    def test_default_ordering_is_newest_first(self):
        self.assertEqual(self._prices({}), ["3.000000000000000000", "2.000000000000000000", "1.000000000000000000"])

    def test_ascending_ordering_is_allowed(self):
        self.assertEqual(
            self._prices({"order_by": "source_timestamp"}),
            ["1.000000000000000000", "2.000000000000000000", "3.000000000000000000"],
        )

    def test_unlisted_order_by_falls_back_to_default(self):
        for order_by in ("asset__symbol", "asset__holdings__quantity", "nonexistent"):
            with self.subTest(order_by=order_by):
                self.assertEqual(
                    self._prices({"order_by": order_by}),
                    ["3.000000000000000000", "2.000000000000000000", "1.000000000000000000"],
                )

    def test_non_numeric_max_points_is_ignored(self):
        self.assertEqual(len(self._prices({"max_points": "abc"})), 3)

    def test_max_points_samples_rows(self):
        self.assertEqual(self._prices({"max_points": "2"}), ["3.000000000000000000", "1.000000000000000000"])

    def test_date_bounds_are_calendar_days_with_an_inclusive_end(self):
        self.assertEqual(self._prices({"start_date": "2026-09-02"}), ["3.000000000000000000", "2.000000000000000000"])
        self.assertEqual(self._prices({"end_date": "2026-09-02"}), ["2.000000000000000000", "1.000000000000000000"])
        self.assertEqual(
            self._prices({"start_date": "2026-09-02", "end_date": "2026-09-02", "order_by": "source_timestamp"}),
            ["2.000000000000000000"],
        )

    def test_malformed_dates_are_a_client_error(self):
        response = self.client.get(self.url, {"start_date": "2026-09-01T12:00:00"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "start_date and end_date must be YYYY-MM-DD.")
