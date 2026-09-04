import django_filters

from users.models.favourite_asset import FavouriteAsset
from users.models.notification import Notification


class FavouriteAssetFilter(django_filters.FilterSet):
    user_account = django_filters.UUIDFilter(field_name="user_account__uuid")
    asset = django_filters.UUIDFilter(field_name="asset__uuid")
    asset_symbol = django_filters.CharFilter(field_name="asset__symbol", lookup_expr="iexact")
    date_from = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = FavouriteAsset
        fields = []


class NotificationFilter(django_filters.FilterSet):
    notification_type = django_filters.CharFilter()
    is_read = django_filters.BooleanFilter()
    is_archived = django_filters.BooleanFilter()

    class Meta:
        model = Notification
        fields = []
