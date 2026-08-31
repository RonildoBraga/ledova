import django_filters

from wallets.models import HoldingSnapshot, Transaction, Wallet


class WalletFilter(django_filters.FilterSet):
    chain = django_filters.CharFilter(field_name="chain", lookup_expr="iexact")
    verification_status = django_filters.CharFilter()
    address = django_filters.CharFilter(field_name="address", lookup_expr="iexact")
    user_account = django_filters.UUIDFilter(field_name="user_account__uuid")

    class Meta:
        model = Wallet
        fields = []


class TransactionFilter(django_filters.FilterSet):
    chain = django_filters.CharFilter(field_name="chain", lookup_expr="iexact")
    wallet = django_filters.UUIDFilter(field_name="wallet__uuid")
    asset = django_filters.UUIDFilter(field_name="asset__uuid")
    address = django_filters.CharFilter(method="filter_address")
    direction = django_filters.CharFilter(method="filter_direction")
    start_date = django_filters.DateTimeFilter(field_name="block_timestamp", lookup_expr="gte")
    end_date = django_filters.DateTimeFilter(field_name="block_timestamp", lookup_expr="lte")

    class Meta:
        model = Transaction
        fields = []

    def filter_address(self, queryset, name, value):
        return queryset.filter_by_address(value)

    def filter_direction(self, queryset, name, value):
        wallet_uuid = self.data.get("wallet")
        return queryset.filter_by_direction(value, wallet_uuid)


class HoldingSnapshotFilter(django_filters.FilterSet):
    holding = django_filters.UUIDFilter(field_name="holding__uuid")
    wallet = django_filters.UUIDFilter(field_name="holding__wallet__uuid")
    asset = django_filters.UUIDFilter(field_name="holding__asset__uuid")
    reason = django_filters.CharFilter(field_name="snapshot_reason")
    start_date = django_filters.DateTimeFilter(field_name="snapshot_date", lookup_expr="gte")
    end_date = django_filters.DateTimeFilter(field_name="snapshot_date", lookup_expr="lte")

    class Meta:
        model = HoldingSnapshot
        fields = []
