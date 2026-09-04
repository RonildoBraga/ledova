from django.db.models import QuerySet


class HoldingSnapshotQuerySet(QuerySet):
    def filter_by_wallet(self, wallet):
        if wallet:
            if hasattr(wallet, "uuid"):
                return self.filter(holding__wallet__uuid=wallet.uuid)
            return self.filter(holding__wallet=wallet)
        return self

    def filter_by_wallets(self, wallets):
        if wallets is not None:
            return self.filter(holding__wallet__in=wallets)
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        queryset = self
        if start_date:
            queryset = queryset.filter(snapshot_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(snapshot_date__lte=end_date)
        return queryset

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(holding__wallet__user_account__user_profiles__user=user)

    def with_optimized_data(self):
        return self.select_related("holding", "holding__wallet", "holding__asset", "caused_by_transaction")
