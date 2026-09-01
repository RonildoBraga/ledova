from rest_framework import serializers

from wallets.models import FiatTransaction


class FiatTransactionSerializer(serializers.ModelSerializer):
    wallet_address = serializers.CharField(source="wallet.address", read_only=True)
    chain = serializers.CharField(source="wallet.chain", read_only=True)

    class Meta:
        model = FiatTransaction
        fields = [
            "uuid",
            "external_id",
            "wallet",
            "wallet_address",
            "chain",
            "fiat_amount",
            "fiat_currency",
            "crypto_amount",
            "crypto_currency",
            "status",
            "payment_method",
            "transaction_hash",
            "provider_fee",
            "network_fee",
            "completed_at",
            "failed_at",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
