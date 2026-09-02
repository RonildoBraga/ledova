from django.db.models import QuerySet


class AssetAllocationQuerySet(QuerySet):
    def filter_by_portfolio(self, portfolio):
        if portfolio:
            if portfolio.uuid:
                return self.filter(portfolio__uuid=portfolio.uuid)
        return self

    def filter_active_assets(self):
        return self.filter(asset__is_active=True)

    def exclude_zero_allocations(self):
        return self.filter(percentage__gt=0)

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(portfolio__user_account__user_profiles__user=user)

    def with_allocation_data(self):
        return self.select_related("portfolio", "asset").filter(asset__is_active=True, percentage__gt=0)
