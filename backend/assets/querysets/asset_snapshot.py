from datetime import datetime, time

from django.db.models import QuerySet
from django.utils.dateparse import parse_date, parse_datetime


class AssetSnapshotQuerySet(QuerySet):
    def filter_by_asset(self, asset_uuid):
        if asset_uuid:
            return self.filter(asset__uuid=asset_uuid)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        queryset = self

        start_datetime = self._parse_date_param(start_date, use_day_start=True)
        if start_datetime:
            queryset = queryset.filter(source_timestamp__gte=start_datetime)

        end_datetime = self._parse_date_param(end_date, use_day_start=False)
        if end_datetime:
            queryset = queryset.filter(source_timestamp__lte=end_datetime)

        return queryset

    def _parse_date_param(self, date_value, use_day_start=True):
        if date_value is None:
            return None

        if isinstance(date_value, datetime):
            return date_value

        if hasattr(date_value, "year") and hasattr(date_value, "month") and hasattr(date_value, "day"):
            return datetime.combine(date_value, time.min if use_day_start else time.max)

        if isinstance(date_value, str):
            parsed_datetime = parse_datetime(date_value)
            if parsed_datetime:
                return parsed_datetime

            parsed_date = parse_date(date_value)
            if parsed_date:
                return datetime.combine(parsed_date, time.min if use_day_start else time.max)

        return None

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
        from decimal import Decimal

        snapshot = self.closest_to_timestamp(timestamp)
        if snapshot:
            return Decimal(str(snapshot.price))
        return None

    def sample_evenly(self, max_points):
        if not max_points:
            return self
        try:
            max_points = int(max_points)
        except (ValueError, TypeError):
            return self
        if max_points <= 0:
            return self

        pks = list(self.values_list("pk", flat=True))
        total = len(pks)
        if total <= max_points:
            return self

        step = (total - 1) / (max_points - 1)
        sampled_pks = [pks[round(i * step)] for i in range(max_points)]
        return self.filter(pk__in=sampled_pks)
