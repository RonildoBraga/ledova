import django_filters

from portfolios.models import AssetAllocation, Portfolio


class PortfolioFilter(django_filters.FilterSet):
    user_account = django_filters.UUIDFilter(field_name="user_account__uuid")
    user_profile = django_filters.UUIDFilter(field_name="user_account__user_profile__uuid")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Portfolio
        fields = []


class AssetAllocationFilter(django_filters.FilterSet):
    portfolio_uuid = django_filters.UUIDFilter(field_name="portfolio__uuid")
    asset_uuid = django_filters.UUIDFilter(field_name="asset__uuid")

    class Meta:
        model = AssetAllocation
        fields = []
