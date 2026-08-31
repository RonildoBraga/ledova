import django_filters

from assets.models import Asset


class AssetFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(field_name="symbol", lookup_expr="iexact")
    asset_type = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Asset
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.search(value)
