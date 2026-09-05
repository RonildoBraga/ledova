from rest_framework import serializers

from whitelist.models import WhitelistEntry


class WhitelistEntrySerializer(serializers.ModelSerializer):
    wallet_address = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WhitelistEntry
        fields = [
            "uuid",
            "wallet_address",
            "label",
            "status",
            "status_display",
            "is_whitelisted",
            "on_chain_timestamp",
            "last_synced_at",
            "add_tx_hash",
            "remove_tx_hash",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "is_whitelisted",
            "on_chain_timestamp",
            "last_synced_at",
            "add_tx_hash",
            "remove_tx_hash",
            "created_at",
            "updated_at",
        ]


class WhitelistStatusSerializer(serializers.Serializer):
    address = serializers.CharField()
    is_whitelisted = serializers.BooleanField()
    can_receive = serializers.BooleanField()


class WhitelistAddSerializer(serializers.Serializer):
    wallet_address = serializers.CharField(
        max_length=42,
        help_text="Ethereum wallet address (0x...)",
    )

    def validate_wallet_address(self, value):
        if not value.startswith("0x"):
            raise serializers.ValidationError("Wallet address must start with '0x'")
        if len(value) != 42:
            raise serializers.ValidationError("Wallet address must be 42 characters (including '0x')")
        try:
            int(value, 16)
        except ValueError:
            raise serializers.ValidationError("Wallet address must contain only hexadecimal characters")
        return value.lower()


class WhitelistAddResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    tx_hash = serializers.CharField()
    entry = WhitelistEntrySerializer()


class WhitelistRemoveSerializer(serializers.Serializer):
    wallet_address = serializers.CharField(
        max_length=42,
        help_text="Ethereum wallet address to remove",
    )

    def validate_wallet_address(self, value):
        if not value.startswith("0x"):
            raise serializers.ValidationError("Wallet address must start with '0x'")
        if len(value) != 42:
            raise serializers.ValidationError("Wallet address must be 42 characters")
        return value.lower()


class WhitelistRemoveResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    tx_hash = serializers.CharField()
    message = serializers.CharField()


class WhitelistSyncResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    entry = WhitelistEntrySerializer()
    message = serializers.CharField()
