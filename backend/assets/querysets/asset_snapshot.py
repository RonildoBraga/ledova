from datetime import datetime, time

from django.db.models import QuerySet
from django.utils.dateparse import parse_date, parse_datetime


class AssetSnapshotQuerySet(QuerySet):
    def filter_by_asset(self, asset_uuid):
        """Kept for external callers (e.g. portfolios/services/sync.py)."""
        if asset_uuid:
            return self.filter(asset__uuid=asset_uuid)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        """Complex date parsing — kept as method for external callers."""
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

    def filter_by_price_range(self, min_price=None, max_price=None):
        queryset = self

        min_price_value = None
        if min_price is not None:
            try:
                min_price_value = float(min_price)
            except (ValueError, TypeError):
                min_price_value = None

        max_price_value = None
        if max_price is not None:
            try:
                max_price_value = float(max_price)
            except (ValueError, TypeError):
                max_price_value = None

        if min_price_value:
            queryset = queryset.filter(price__gte=min_price_value)
        if max_price_value:
            queryset = queryset.filter(price__lte=max_price_value)
        return queryset

    def filter_by_exchange(self, exchange_short_name):
        """Kept for manager proxy."""
        if exchange_short_name:
            return self.filter(asset__exchange__short_name=exchange_short_name)
        return self

    def active_assets_only(self):
        return self.filter(asset__is_active=True)

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
        """Return evenly-distributed sample of max_points rows."""
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
