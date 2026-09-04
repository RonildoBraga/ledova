from rest_framework import serializers

from assets.serializers import AssetSerializer
from wallets.models import Holding


class HoldingSerializer(serializers.ModelSerializer):
    wallet_uuid = serializers.CharField(source="wallet.uuid", read_only=True)
    wallet_address = serializers.CharField(source="wallet.address", read_only=True)
    asset_uuid = serializers.CharField(source="asset.uuid", read_only=True)
    asset_symbol = serializers.CharField(source="asset.symbol", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    market_value = serializers.DecimalField(max_digits=40, decimal_places=2, read_only=True)
    asset = AssetSerializer(read_only=True, required=False)

    class Meta:
        model = Holding
        fields = (
            "uuid",
            "wallet_uuid",
            "wallet_address",
            "asset_uuid",
            "asset_symbol",
            "asset_name",
            "asset",
            "quantity",
            "market_value",
            "last_synced_block",
            "last_synced_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
