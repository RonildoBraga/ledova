from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user


class HoldingQuerySet(QuerySet):
    def filter_by_wallets(self, wallets):
        if wallets is not None:
            return self.filter(wallet__in=wallets)
        return self

    def with_positive_quantity(self):
        return self.filter(quantity__gt=0)

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "wallets.view_holding", klass=self)

    def active_assets_only(self):
        return self.filter(asset__is_active=True)

    def verified_assets_only(self):
        return self.filter(asset__is_verified=True)

    def with_optimized_data(self):
        return self.select_related("wallet", "asset")

    def zero_out(self):
        return self.update(quantity=Decimal("0"), last_synced_at=timezone.now())
