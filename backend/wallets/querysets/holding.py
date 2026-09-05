from django.db.models import QuerySet


class HoldingQuerySet(QuerySet):
    def active_assets_only(self):
        return self.filter(asset__is_active=True, asset__is_verified=True)
