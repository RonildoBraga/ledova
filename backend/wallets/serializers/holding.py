from rest_framework import serializers

from assets.choices import VALUE_SOURCE_CHOICES
from assets.serializers import AssetSerializer
from wallets.models import Holding


class HoldingSerializer(serializers.ModelSerializer):
    wallet_uuid = serializers.CharField(source="wallet.uuid", read_only=True)
    wallet_address = serializers.CharField(source="wallet.address", read_only=True)
    chain = serializers.CharField(source="wallet.chain", read_only=True)
    asset_uuid = serializers.CharField(source="asset.uuid", read_only=True)
    asset_symbol = serializers.CharField(source="asset.symbol", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    market_value = serializers.DecimalField(max_digits=40, decimal_places=2, read_only=True)
    value_source = serializers.ChoiceField(choices=VALUE_SOURCE_CHOICES, read_only=True)
    asset = AssetSerializer(read_only=True, required=False)

    class Meta:
        model = Holding
        fields = (
            "uuid",
            "wallet_uuid",
            "wallet_address",
            "chain",
            "asset_uuid",
            "asset_symbol",
            "asset_name",
            "asset",
            "quantity",
            "market_value",
            "value_source",
            "last_synced_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
