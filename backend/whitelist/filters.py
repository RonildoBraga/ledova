import django_filters

from whitelist.models import WhitelistEntry


class WhitelistEntryFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    is_whitelisted = django_filters.BooleanFilter()
    date_from = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = WhitelistEntry
        fields = []
