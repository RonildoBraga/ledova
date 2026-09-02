from django.db.models import QuerySet

from shared.utils.datetime_utils import (
    parse_date_to_timezone_aware,
    parse_end_date_inclusive,
)


class PortfolioSnapshotQuerySet(QuerySet):
    def filter_by_portfolio(self, portfolio):
        if portfolio:
            if hasattr(portfolio, "uuid"):
                return self.filter(portfolio__uuid=portfolio.uuid)
            return self.filter(portfolio=portfolio)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        """End of range is exclusive (snapshot_date__lt)."""
        queryset = self

        if start_date:
            start_date = parse_date_to_timezone_aware(start_date)
            queryset = queryset.filter(snapshot_date__gte=start_date)

        if end_date:
            end_date = parse_end_date_inclusive(end_date)
            queryset = queryset.filter(snapshot_date__lt=end_date)

        return queryset

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(portfolio__user_account__user_profiles__user=user)

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
        # Preserve the original queryset ordering after filtering by sampled PKs
        ordering = self.query.order_by or ("snapshot_date",)
        return self.filter(pk__in=sampled_pks).order_by(*ordering)

    def with_optimized_data(self):
        return self.select_related("portfolio", "portfolio__user_account")

    def daily_snapshots(self):
        return self.filter(snapshot_reason="DAILY")

    def for_date(self, date):
        if date:
            return self.filter(snapshot_date=date)
        return self
