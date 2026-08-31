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
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(holding__wallet__user_account__user_profiles__user=user)

    def with_optimized_data(self):
        return self.select_related("holding", "holding__wallet", "holding__asset", "caused_by_transaction")

    def daily_only(self):
        return self.filter(snapshot_reason="DAILY")

    def balance_sync_only(self):
        return self.filter(snapshot_reason="BALANCE_SYNC")

    def swap_only(self):
        return self.filter(snapshot_reason="SWAP")

    def transfer_only(self):
        return self.filter(snapshot_reason__in=["TRANSFER_IN", "TRANSFER_OUT"])

    def latest_for_holding(self, holding):
        return self.filter(holding=holding).order_by("-snapshot_date").first()

    def oldest_for_holding(self, holding):
        return self.filter(holding=holding).order_by("snapshot_date").first()
