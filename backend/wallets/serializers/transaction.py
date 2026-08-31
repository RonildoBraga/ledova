from rest_framework import serializers

from assets.models import Asset
from wallets.models import Transaction, Wallet


class TransactionSerializer(serializers.ModelSerializer):
    uuid = serializers.CharField(read_only=True)
    chain = serializers.CharField()
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none())
    wallet = serializers.PrimaryKeyRelatedField(queryset=Wallet.objects.none())
    asset_symbol = serializers.CharField(source="asset.symbol", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    wallet_address = serializers.CharField(source="wallet.address", read_only=True)

    class Meta:
        model = Transaction
        fields = (
            "uuid",
            "tx_hash",
            "chain",
            "from_address",
            "to_address",
            "asset",
            "asset_symbol",
            "asset_name",
            "amount",
            "market_value",
            "block_timestamp",
            "block_number",
            "status",
            "transaction_fee_estimated",
            "transaction_fee",
            "wallet",
            "wallet_address",
            "created_at",
        )
        read_only_fields = (
            "uuid",
            "created_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        fields["asset"].queryset = Asset.objects.all()
        fields["wallet"].queryset = Wallet.objects.all()
        return fields
