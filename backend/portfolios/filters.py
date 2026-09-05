import django_filters

from portfolios.models import Portfolio


class PortfolioFilter(django_filters.FilterSet):
    user_account = django_filters.UUIDFilter(field_name="user_account__uuid")
    user_profile = django_filters.UUIDFilter(field_name="user_account__user_profiles__uuid")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Portfolio
        fields = []
