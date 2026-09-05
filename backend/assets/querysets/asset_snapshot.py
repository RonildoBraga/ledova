from decimal import Decimal

from django.db.models import QuerySet

from shared.utils.datetime_utils import (
    parse_date_to_timezone_aware,
    parse_end_date_inclusive,
)


class AssetSnapshotQuerySet(QuerySet):
    def filter_by_asset(self, asset_uuid):
        if asset_uuid:
            return self.filter(asset__uuid=asset_uuid)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        queryset = self
        if start_date:
            queryset = queryset.filter(source_timestamp__gte=parse_date_to_timezone_aware(start_date))
        if end_date:
            queryset = queryset.filter(source_timestamp__lt=parse_end_date_inclusive(end_date))
        return queryset

    def closest_to_timestamp(self, timestamp):
        if not timestamp:
            return None

        snapshot_before = self.filter(source_timestamp__lte=timestamp).order_by("-source_timestamp").first()
        snapshot_after = self.filter(source_timestamp__gte=timestamp).order_by("source_timestamp").first()

        if snapshot_before and snapshot_after:
            diff_before = abs((timestamp - snapshot_before.source_timestamp).total_seconds())
            diff_after = abs((snapshot_after.source_timestamp - timestamp).total_seconds())
            return snapshot_before if diff_before <= diff_after else snapshot_after

        return snapshot_before or snapshot_after

    def get_price_at_timestamp(self, timestamp):
        snapshot = self.closest_to_timestamp(timestamp)
        if snapshot:
            return Decimal(str(snapshot.price))
        return None
