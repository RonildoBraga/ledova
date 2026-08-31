from rest_framework import serializers

from tokens.models import SwapOrder


class SwapOrderListSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    share_token_symbol = serializers.CharField(source="share_token.symbol", read_only=True)
    share_token_name = serializers.CharField(source="share_token.name", read_only=True)
    payment_token_symbol = serializers.CharField(source="payment_token.symbol", read_only=True)
    sell_order_uuid = serializers.UUIDField(source="sell_order.uuid", read_only=True)
    buy_order_uuid = serializers.UUIDField(source="buy_order.uuid", read_only=True)
    seller_has_signed = serializers.BooleanField(read_only=True)
    buyer_has_signed = serializers.BooleanField(read_only=True)

    class Meta:
        model = SwapOrder
        fields = [
            "uuid",
            "status",
            "status_display",
            "share_token_symbol",
            "share_token_name",
            "payment_token_symbol",
            "seller_address",
            "buyer_address",
            "share_amount",
            "payment_amount",
            "sell_order_uuid",
            "buy_order_uuid",
            "seller_has_signed",
            "buyer_has_signed",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields


class SwapOrderDetailSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    share_token_symbol = serializers.CharField(source="share_token.symbol", read_only=True)
    share_token_name = serializers.CharField(source="share_token.name", read_only=True)
    share_token_address = serializers.CharField(source="share_token.contract_address", read_only=True)
    payment_token_symbol = serializers.CharField(source="payment_token.symbol", read_only=True)
    payment_token_address = serializers.CharField(source="payment_token.contract_address", read_only=True)
    sell_order_uuid = serializers.UUIDField(source="sell_order.uuid", read_only=True)
    buy_order_uuid = serializers.UUIDField(source="buy_order.uuid", read_only=True)
    seller_has_signed = serializers.BooleanField(read_only=True)
    buyer_has_signed = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_ready = serializers.BooleanField(read_only=True)

    class Meta:
        model = SwapOrder
        fields = [
            "uuid",
            "status",
            "status_display",
            "share_token_symbol",
            "share_token_name",
            "share_token_address",
            "payment_token_symbol",
            "payment_token_address",
            "seller_address",
            "buyer_address",
            "share_amount",
            "payment_amount",
            "nonce",
            "order_hash",
            "seller_has_signed",
            "buyer_has_signed",
            "is_expired",
            "is_ready",
            "sell_order_uuid",
            "buy_order_uuid",
            "tx_hash",
            "expires_at",
            "completed_at",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SwapTypedDataSerializer(serializers.Serializer):

    types = serializers.DictField()
    primaryType = serializers.CharField()
    domain = serializers.DictField()
    message = serializers.DictField()


class SwapDataResponseSerializer(serializers.Serializer):

    swap_order = SwapOrderDetailSerializer()
    typed_data = SwapTypedDataSerializer()
    user_role = serializers.ChoiceField(choices=["seller", "buyer"])
    has_signed = serializers.BooleanField()


class SubmitSignatureSerializer(serializers.Serializer):

    signature = serializers.CharField(min_length=130, max_length=132)
    signer_address = serializers.CharField(max_length=42)

    def validate_signature(self, value):
        if not value.startswith("0x"):
            raise serializers.ValidationError("Signature must start with 0x")
        sig_hex = value[2:]
        if len(sig_hex) != 130:
            raise serializers.ValidationError("Invalid signature length")
        try:
            bytes.fromhex(sig_hex)
        except ValueError:
            raise serializers.ValidationError("Invalid hexadecimal signature")
        return value

    def validate_signer_address(self, value):
        if not value.startswith("0x") or len(value) != 42:
            raise serializers.ValidationError("Invalid Ethereum address format")
        return value
