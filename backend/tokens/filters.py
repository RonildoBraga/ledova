import django_filters
from django_filters import CharFilter

from tokens.models import CapitalIncreaseRequest, ShareToken, TransferOrder


class CommaSeparatedCharFilter(CharFilter):

    def filter(self, qs, value):
        if not value:
            return qs
        values = [v.strip() for v in value.split(",") if v.strip()]
        if len(values) == 1:
            return qs.filter(**{self.field_name: values[0]})
        return qs.filter(**{f"{self.field_name}__in": values})


class ShareTokenFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    token_type = django_filters.CharFilter()
    company_uuid = django_filters.UUIDFilter(field_name="company__uuid")
    contract_address = django_filters.CharFilter(lookup_expr="iexact")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = ShareToken
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.search(value)


class TransferOrderFilter(django_filters.FilterSet):
    token = django_filters.UUIDFilter(field_name="token__uuid")
    status = CommaSeparatedCharFilter()
    order_type = django_filters.CharFilter()
    wallet_address = django_filters.CharFilter(lookup_expr="iexact")
    payment_token = django_filters.UUIDFilter(field_name="payment_token__uuid")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = TransferOrder
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.search(value)


class CapitalIncreaseFilter(django_filters.FilterSet):
    token = django_filters.UUIDFilter(field_name="token__uuid")
    company = django_filters.UUIDFilter(field_name="token__company__uuid")
    status = django_filters.CharFilter()
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = CapitalIncreaseRequest
        fields = []

    def filter_search(self, queryset, name, value):
        return queryset.search(value)
