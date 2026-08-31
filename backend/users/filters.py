import django_filters

from users.models.favourite_asset import FavouriteAsset
from users.models.notification import Notification
from users.models.user_profile import UserProfile


class UserProfileFilter(django_filters.FilterSet):
    verified = django_filters.BooleanFilter(field_name="is_id_verified")
    terms_accepted = django_filters.BooleanFilter(field_name="terms_and_conditions")
    name = django_filters.CharFilter(field_name="full_name", lookup_expr="icontains")
    dob = django_filters.DateFilter(field_name="date_of_birth")
    risk_tolerance = django_filters.CharFilter()
    date_from = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = UserProfile
        fields = []


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
