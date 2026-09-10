from drf_spectacular.utils import inline_serializer
from rest_framework import serializers

from wallets.serializers.actions import PreparedEvmTransactionSerializer


class ApprovalStatusResponseSerializer(serializers.Serializer):
    swap_uuid = serializers.UUIDField()
    user_role = serializers.ChoiceField(choices=("buyer", "seller"))
    token_address = serializers.CharField()
    token_symbol = serializers.CharField()
    required_amount = serializers.IntegerField()
    current_allowance = serializers.IntegerField()
    needs_approval = serializers.BooleanField()
    spender = serializers.CharField()


class SufficientApprovalResponseSerializer(serializers.Serializer):
    needs_approval = serializers.BooleanField()
    message = serializers.CharField()
    current_allowance = serializers.IntegerField()
    required_amount = serializers.IntegerField()


class ApprovalTransactionResponseSerializer(serializers.Serializer):
    needs_approval = serializers.BooleanField()
    swap_uuid = serializers.UUIDField()
    user_role = serializers.ChoiceField(choices=("buyer", "seller"))
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
    unlimited = serializers.BooleanField()


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
