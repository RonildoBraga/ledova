from rest_framework import serializers

from assets.models import (
    Asset,
    AssetChainDeployment,
    AssetSnapshot,
)
from shared.models.country import Country


class AssetChainDeploymentSerializer(serializers.ModelSerializer):

    class Meta:
        model = AssetChainDeployment
        fields = ("uuid", "chain", "contract_address", "decimals", "is_active")
        read_only_fields = ("uuid",)


class CountrySerializer(serializers.ModelSerializer):

    class Meta:
        model = Country
        fields = (
            "uuid",
            "name",
            "code",
            "dial_code",
            "is_available",
        )
        read_only_fields = ("uuid",)


class AssetSerializer(serializers.ModelSerializer):

    asset_type_display = serializers.SerializerMethodField()
    chain = serializers.SerializerMethodField()
    contract_address = serializers.SerializerMethodField()
    chain_deployments = AssetChainDeploymentSerializer(many=True, read_only=True)
    nav_per_token = serializers.SerializerMethodField()
    last_nav_update = serializers.SerializerMethodField()
    is_yield_token = serializers.SerializerMethodField()

    def get_chain(self, obj):
        dep = obj.chain_deployments.first()
        return dep.chain if dep else None

    def get_contract_address(self, obj):
        dep = obj.chain_deployments.first()
        return dep.contract_address if dep else None

    def get_asset_type_display(self, obj):
        type_mapping = {
            "native_crypto": "Crypto",
            "stablecoin": "Stablecoin",
            "token": "Token",
            "tokenized_security": "Tokenized Security",
            "tokenized_rwa": "Tokenized RWA",
            "synthetic": "Synthetic",
        }
        return type_mapping.get(obj.asset_type, obj.asset_type.replace("_", " ").title())

    def _get_yield_token(self, obj):
        if not hasattr(obj, "_yield_token_cache"):
            from tokens.models import YieldToken

            obj._yield_token_cache = YieldToken.objects.filter(symbol=obj.symbol, is_active=True).first()
        return obj._yield_token_cache

    def get_nav_per_token(self, obj):
        yt = self._get_yield_token(obj)
        return str(yt.nav_per_token) if yt and yt.nav_per_token else None

    def get_last_nav_update(self, obj):
        yt = self._get_yield_token(obj)
        return yt.last_nav_update.isoformat() if yt and yt.last_nav_update else None

    def get_is_yield_token(self, obj):
        return self._get_yield_token(obj) is not None

    class Meta:
        model = Asset
        fields = (
            "uuid",
            "symbol",
            "name",
            "asset_type",
            "asset_type_display",
            "chain",
            "contract_address",
            "decimals",
            "chain_deployments",
            "nav_per_token",
            "last_nav_update",
            "is_yield_token",
            "current_price",
            "price_currency",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "asset_type_display",
            "nav_per_token",
            "last_nav_update",
            "is_yield_token",
            "current_price",
            "created_at",
            "updated_at",
        )


class AssetSnapshotSerializer(serializers.ModelSerializer):

    asset = serializers.StringRelatedField(read_only=True)
    asset_symbol = serializers.CharField(source="asset.symbol", read_only=True)

    class Meta:
        model = AssetSnapshot
        fields = (
            "uuid",
            "asset",
            "asset_symbol",
            "price",
            "price_currency",
            "market_data",
            "source_timestamp",
            "data_source",
            "block_number",
            "tx_hash",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "asset",
            "asset_symbol",
            "created_at",
            "updated_at",
        )
