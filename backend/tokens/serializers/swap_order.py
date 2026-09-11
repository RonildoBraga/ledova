from rest_framework import serializers

from operators.settlement import deployment_for
from tokens.models import SwapOrder
from tokens.services.settlement_context import recorded_settlement_context


class RecordedSwapDisplay:
    def to_representation(self, instance):
        if not instance.settlement_protocol_version:
            return super().to_representation(instance)
        context = recorded_settlement_context(instance)
        display = {
            "share_token_symbol": context["share_token"]["symbol"],
            "share_token_name": context["share_token"]["name"],
            "share_token_address": context["share_token"]["address"],
            "payment_token_symbol": context["payment_asset"]["symbol"],
            "payment_token_address": context["payment_asset"]["deployment_address"],
            "sell_order_uuid": str(instance.sell_order_id),
            "buy_order_uuid": str(instance.buy_order_id),
        }
        result = {}
        for name, field in self.fields.items():
            if name in display:
                result[name] = display[name]
            else:
                value = field.get_attribute(instance)
                result[name] = None if value is None else field.to_representation(value)
        return result


class SwapOrderListSerializer(RecordedSwapDisplay, serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    share_token_symbol = serializers.CharField(source="share_token.symbol", read_only=True)
    share_token_name = serializers.CharField(source="share_token.name", read_only=True)
    payment_token_symbol = serializers.CharField(source="payment_asset.symbol", read_only=True)
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


class SwapOrderDetailSerializer(RecordedSwapDisplay, serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    share_token_symbol = serializers.CharField(source="share_token.symbol", read_only=True)
    share_token_name = serializers.CharField(source="share_token.name", read_only=True)
    share_token_address = serializers.CharField(source="share_token.contract_address", read_only=True)
    payment_token_symbol = serializers.CharField(source="payment_asset.symbol", read_only=True)
    payment_token_address = serializers.SerializerMethodField()
    sell_order_uuid = serializers.UUIDField(source="sell_order.uuid", read_only=True)
    buy_order_uuid = serializers.UUIDField(source="buy_order.uuid", read_only=True)
    seller_has_signed = serializers.BooleanField(read_only=True)
    buyer_has_signed = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_ready = serializers.BooleanField(read_only=True)

    def get_payment_token_address(self, swap_order) -> str:
        deployment = deployment_for(swap_order.payment_asset)
        return deployment.contract_address if deployment else ""

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
            "settlement_protocol_version",
            "settlement_context",
            "settlement_digest",
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


class SettlementIdentitySerializer(serializers.Serializer):
    swap_uuid = serializers.UUIDField()
    owner_account_uuid = serializers.UUIDField()
    wallet_uuid = serializers.UUIDField()
    settlement_digest = serializers.RegexField(r"^0x[0-9a-f]{64}$", required=False)


class SettlementWriteIdentitySerializer(SettlementIdentitySerializer):
    settlement_digest = serializers.RegexField(r"^0x[0-9a-f]{64}$")


class SettlementSignatureSerializer(SettlementWriteIdentitySerializer, SubmitSignatureSerializer):
    signer_address = serializers.RegexField(r"^0x[0-9a-fA-F]{40}$")


class SettlementApprovalBroadcastSerializer(SettlementWriteIdentitySerializer):
    signed_transaction = serializers.RegexField(r"^(0x)?[0-9a-fA-F]+$", max_length=32768)
