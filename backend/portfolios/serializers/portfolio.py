from rest_framework import serializers

from assets.models import Asset
from portfolios.models.portfolio import (
    AssetAllocation,
    Portfolio,
    PortfolioSnapshot,
)
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


class AssetAllocationSerializer(serializers.ModelSerializer):
    portfolio = serializers.PrimaryKeyRelatedField(queryset=Portfolio.objects.none())
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none())
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    asset_symbol = serializers.CharField(source="asset.symbol", read_only=True)
    asset_display_name = serializers.CharField(source="asset.display_name", read_only=True)
    asset_sector = serializers.SerializerMethodField()
    asset_industry = serializers.SerializerMethodField()
    asset_exchange = serializers.SerializerMethodField()
    asset_currency = serializers.CharField(source="asset.currency", read_only=True)

    def get_asset_sector(self, obj):
        return obj.asset.sector.name if hasattr(obj.asset, "sector") and obj.asset.sector else None

    def get_asset_industry(self, obj):
        return obj.asset.industry.name if hasattr(obj.asset, "industry") and obj.asset.industry else None

    def get_asset_exchange(self, obj):
        return obj.asset.exchange.name if hasattr(obj.asset, "exchange") and obj.asset.exchange else None

    quantity = serializers.IntegerField(read_only=True, required=False)
    allocation_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, required=False)
    market_value = serializers.DecimalField(max_digits=19, decimal_places=4, read_only=True, required=False)

    class Meta:
        model = AssetAllocation
        fields = (
            "uuid",
            "portfolio",
            "asset",
            "asset_name",
            "asset_symbol",
            "asset_display_name",
            "asset_sector",
            "asset_industry",
            "asset_exchange",
            "asset_currency",
            "percentage",
            "quantity",
            "allocation_percentage",
            "market_value",
        )
        read_only_fields = (
            "uuid",
            "asset_name",
            "asset_symbol",
            "asset_display_name",
            "asset_sector",
            "asset_industry",
            "asset_exchange",
            "asset_currency",
            "quantity",
            "allocation_percentage",
            "market_value",
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            fields["portfolio"].queryset = Portfolio.objects.none()
        else:
            fields["portfolio"].queryset = Portfolio.objects.visible_to_user(request.user).active()
        fields["asset"].queryset = Asset.objects.all()
        return fields


class PortfolioSnapshotSerializer(serializers.ModelSerializer):
    portfolio_name = serializers.CharField(source="portfolio.name", read_only=True)
    account_id = serializers.CharField(source="portfolio.user_account.uuid", read_only=True)
    has_value_data = serializers.BooleanField(read_only=True)

    def _has_account_scoped_holdings(self, obj):
        portfolio_id = obj.portfolio_id
        if not hasattr(self, "_allowed_wallet_ids_by_portfolio"):
            self._allowed_wallet_ids_by_portfolio = {}

        if portfolio_id not in self._allowed_wallet_ids_by_portfolio:
            self._allowed_wallet_ids_by_portfolio[portfolio_id] = set(
                obj.portfolio.user_account.wallets.values_list("uuid", flat=True)
            )

        return obj.has_account_scoped_holdings(self._allowed_wallet_ids_by_portfolio[portfolio_id])

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if not self._has_account_scoped_holdings(instance):
            # Legacy snapshots may predate account-scoped collection. Keep their
            # metadata visible, but quarantine all embedded holdings and values.
            representation["holdings_data"] = {}
            representation["total_market_value"] = None
            representation["has_value_data"] = False
        return representation

    class Meta:
        model = PortfolioSnapshot
        fields = (
            "uuid",
            "portfolio",
            "portfolio_name",
            "account_id",
            "holdings_data",
            "total_market_value",
            "has_value_data",
            "snapshot_date",
            "snapshot_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "portfolio_name",
            "account_id",
            "holdings_data",
            "total_market_value",
            "has_value_data",
            "created_at",
            "updated_at",
        )
