from rest_framework import serializers


class TradingWalletTokenBalanceSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    balance = serializers.CharField()
    contract_address = serializers.CharField()
    decimals = serializers.IntegerField()
    type = serializers.ChoiceField(choices=("share_token", "stablecoin"))


class TradingWalletBalancesSerializer(serializers.Serializer):
    wallet_address = serializers.CharField()
    balances = TradingWalletTokenBalanceSerializer(many=True)
