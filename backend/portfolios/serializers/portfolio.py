from rest_framework import serializers

from portfolios.models.portfolio import Portfolio
from users.models import UserAccount


class PortfolioSerializer(serializers.ModelSerializer):
    user_account = serializers.PrimaryKeyRelatedField(queryset=UserAccount.objects.none(), required=False)
    wallet_uuids = serializers.SerializerMethodField()
    wallet_count = serializers.SerializerMethodField()

    def get_fields(self):
        fields = super().get_fields()
        # Scope the writable owner FK to the caller's own accounts so a
        # portfolio can never be filed under another tenant's account.
        request = self.context.get("request")
        fields["user_account"].queryset = UserAccount.objects.visible_to_user(getattr(request, "user", None))
        return fields

    def get_wallet_uuids(self, obj):
        return [str(wallet.uuid) for wallet in obj.account_wallets()]

    def get_wallet_count(self, obj):
        return obj.account_wallets().count()

    class Meta:
        model = Portfolio
        fields = (
            "uuid",
            "user_account",
            "name",
            "is_active",
            "wallet_uuids",
            "wallet_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "wallet_uuids",
            "wallet_count",
            "created_at",
            "updated_at",
        )


class PortfolioValuePointSerializer(serializers.Serializer):
    """One computed day of the value series, under the keys the stored snapshot rows carried."""

    uuid = serializers.CharField()
    portfolio = serializers.UUIDField()
    portfolio_name = serializers.CharField()
    account_id = serializers.CharField()
    holdings_data = serializers.DictField()
    total_market_value = serializers.DecimalField(max_digits=40, decimal_places=18, allow_null=True)
    has_value_data = serializers.BooleanField()
    snapshot_date = serializers.DateField()
    snapshot_reason = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
