from rest_framework import serializers

from wallets.models import HoldingSnapshot


class HoldingSnapshotSerializer(serializers.ModelSerializer):
    holding_uuid = serializers.CharField(source="holding.uuid", read_only=True)
    wallet_uuid = serializers.CharField(source="holding.wallet.uuid", read_only=True)
    wallet_address = serializers.CharField(source="holding.wallet.address", read_only=True)
    asset_uuid = serializers.CharField(source="holding.asset.uuid", read_only=True)
    asset_symbol = serializers.CharField(source="holding.asset.symbol", read_only=True)
    asset_name = serializers.CharField(source="holding.asset.name", read_only=True)
    caused_by_transaction_uuid = serializers.CharField(
        source="caused_by_transaction.uuid", read_only=True, allow_null=True
    )
    caused_by_transaction_hash = serializers.CharField(
        source="caused_by_transaction.tx_hash", read_only=True, allow_null=True
    )
    market_value = serializers.DecimalField(max_digits=40, decimal_places=2, read_only=True)

    class Meta:
        model = HoldingSnapshot
        fields = (
            "uuid",
            "holding",
            "holding_uuid",
            "wallet_uuid",
            "wallet_address",
            "asset_uuid",
            "asset_symbol",
            "asset_name",
            "quantity",
            "market_value",
            "block_number",
            "snapshot_date",
            "snapshot_reason",
            "caused_by_transaction",
            "caused_by_transaction_uuid",
            "caused_by_transaction_hash",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
