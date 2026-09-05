from django.db.models import QuerySet


class HoldingQuerySet(QuerySet):
    def filter_by_wallets(self, wallets):
        if wallets is not None:
            return self.filter(wallet__in=wallets)
        return self

    def active_assets_only(self):
        return self.filter(asset__is_active=True, asset__is_verified=True)

    def with_optimized_data(self):
        return self.select_related("wallet", "asset")
