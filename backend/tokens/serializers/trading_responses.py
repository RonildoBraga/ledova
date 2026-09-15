from drf_spectacular.utils import PolymorphicProxySerializer, inline_serializer
from rest_framework import serializers

from tokens.serializers.signing import (
    SettlementContextField,
    SettlementTypedDataSerializer,
)
from tokens.serializers.swap_order import SwapOrderDetailSerializer
from wallets.serializers.actions import PreparedEvmTransactionSerializer


class SettlementResponseIdentitySerializer(serializers.Serializer):
    swap_uuid = serializers.UUIDField()
    order_uuid = serializers.UUIDField()
    owner_account_uuid = serializers.UUIDField()
    wallet_uuid = serializers.UUIDField()
    settlement_digest = serializers.CharField()
    user_role = serializers.ChoiceField(choices=("buyer", "seller"))


class SettlementSwapOrderSerializer(SwapOrderDetailSerializer):
    settlement_protocol_version = serializers.ChoiceField(choices=[1], read_only=True)
    settlement_context = SettlementContextField(read_only=True)


class SettlementSwapOrderForSigningSerializer(SettlementResponseIdentitySerializer):
    swap_order = SettlementSwapOrderSerializer()
    typed_data = SettlementTypedDataSerializer()
    has_signed = serializers.BooleanField()
    can_sign = serializers.BooleanField()
    admission_refusal = serializers.CharField(allow_null=True)


class SettlementApprovalStatusSerializer(SettlementResponseIdentitySerializer):
    token_address = serializers.CharField()
    token_symbol = serializers.CharField()
    required_amount = serializers.CharField()
    current_allowance = serializers.CharField()
    needs_approval = serializers.BooleanField()
    spender = serializers.CharField()


class SettlementSufficientApprovalSerializer(SettlementResponseIdentitySerializer):
    needs_approval = serializers.ChoiceField(choices=[False])
    message = serializers.CharField()
    current_allowance = serializers.CharField()
    required_amount = serializers.CharField()


class SettlementApprovalTransactionSerializer(SettlementResponseIdentitySerializer):
    needs_approval = serializers.ChoiceField(choices=[True])
    transaction = inline_serializer(
        name="ApprovalTransaction",
        fields={
            "to": serializers.CharField(),
            "from": serializers.CharField(),
            "data": serializers.CharField(),
            "value": serializers.CharField(),
            "gas": serializers.CharField(),
            "gasPrice": serializers.CharField(),
            "nonce": serializers.CharField(),
            "chainId": serializers.CharField(),
        },
    )
    description = serializers.CharField()
    token_address = serializers.CharField()
    token_symbol = serializers.CharField()
    spender = serializers.CharField()
    amount = serializers.CharField()
    unlimited = serializers.ChoiceField(choices=[True])


class SettlementApprovalReceiptSerializer(SettlementResponseIdentitySerializer):
    tx_hash = serializers.CharField()
    block_number = serializers.IntegerField(allow_null=True)
    gas_used = serializers.IntegerField(allow_null=True)


class SettlementApprovalUncertainSerializer(SettlementResponseIdentitySerializer):
    tx_hash = serializers.CharField()
    code = serializers.ChoiceField(choices=("swap_approval_unconfirmed",))
    detail = serializers.CharField()


ApprovalDataResponseSerializer = PolymorphicProxySerializer(
    component_name="ApprovalDataResponse",
    serializers=[SettlementSufficientApprovalSerializer, SettlementApprovalTransactionSerializer],
    resource_type_field_name=None,
)


class MarketLastTradeSerializer(serializers.Serializer):
    price = serializers.CharField()
    shares = serializers.IntegerField()
    payment_amount = serializers.CharField()
    payment_token = serializers.CharField()
    completed_at = serializers.DateTimeField(allow_null=True)


class MarketDataSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    symbol = serializers.CharField()
    last_trade = MarketLastTradeSerializer(allow_null=True)
    last_trade_price = serializers.CharField(allow_null=True)
    best_bid = serializers.CharField(allow_null=True)
    best_ask = serializers.CharField(allow_null=True)
    midpoint_price = serializers.CharField(allow_null=True)


class OrderBookEntrySerializer(serializers.Serializer):
    price = serializers.CharField()
    quantity = serializers.IntegerField()
    orders = serializers.IntegerField()


class OrderBookSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    buy_orders = OrderBookEntrySerializer(many=True)
    sell_orders = OrderBookEntrySerializer(many=True)


class TransferTokenInfoSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    symbol = serializers.CharField()
    contract_address = serializers.CharField()


class PreparedTokenTransactionSerializer(PreparedEvmTransactionSerializer):
    data = serializers.CharField()


class PreparedTokenTransferSerializer(serializers.Serializer):
    token = TransferTokenInfoSerializer()
    from_address = serializers.CharField()
    to_address = serializers.CharField()
    amount = serializers.IntegerField()
    transaction_data = PreparedTokenTransactionSerializer()


class TokenTransferReceiptSerializer(serializers.Serializer):
    tx_hash = serializers.CharField()
    block_number = serializers.IntegerField(allow_null=True)
    gas_used = serializers.IntegerField(allow_null=True)
