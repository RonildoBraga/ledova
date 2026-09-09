import django_filters
from django import forms

from shared.constants import SUPPORTED_CHAINS, normalize_chain
from wallets.models import Transaction, Wallet


class ChainAddressFilterForm(forms.Form):
    def clean(self):
        data = super().clean()
        if data.get("chain"):
            data["chain"] = normalize_chain(data["chain"])
            if data["chain"] not in SUPPORTED_CHAINS:
                self.add_error("chain", "Choose a supported network.")
        if data.get("address") and not data.get("chain") and not data.get("wallet"):
            raise forms.ValidationError("An address filter requires a network, or a wallet UUID for transactions.")
        return data


class WalletFilter(django_filters.FilterSet):
    chain = django_filters.CharFilter(field_name="chain", lookup_expr="iexact")
    verification_status = django_filters.CharFilter()
    address = django_filters.CharFilter(method="filter_address")
    user_account = django_filters.UUIDFilter(field_name="user_account__uuid")

    class Meta:
        model = Wallet
        fields = []
        form = ChainAddressFilterForm

    def filter_address(self, queryset, name, value):
        return queryset.filter_by_address(value, chain=self.form.cleaned_data["chain"])


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
        form = ChainAddressFilterForm

    def filter_address(self, queryset, name, value):
        chain = self.form.cleaned_data.get("chain")
        if not chain:
            chain = (
                Wallet.objects.visible_to_user(self.request.user)
                .filter(pk=self.form.cleaned_data["wallet"])
                .values_list("chain", flat=True)
                .first()
            )
        return queryset.filter_by_address(value, chain=chain)

    def filter_direction(self, queryset, name, value):
        wallet_uuid = self.data.get("wallet")
        return queryset.filter_by_direction(value, wallet_uuid)
