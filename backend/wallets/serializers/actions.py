from rest_framework import serializers

from shared.constants import SUPPORTED_CHAINS
from wallets.serializers.wallet import WalletSerializer


class WalletVerificationChallengeSerializer(serializers.Serializer):
    challenge = serializers.CharField()
    message = serializers.CharField()
    wallet_address = serializers.CharField()


class WalletVerificationResultSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    verification_status = serializers.ChoiceField(choices=("PENDING", "VERIFIED"))
    verified_at = serializers.DateTimeField()


class WalletVerificationSignatureSerializer(serializers.Serializer):
    signature = serializers.CharField()


class WalletSyncResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("success", "skipped", "error"))
    transactions = serializers.IntegerField(required=False)
    snapshots = serializers.IntegerField(required=False)
    holdings = serializers.IntegerField(required=False)
    error = serializers.CharField(required=False)


class WalletSyncResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    wallet = WalletSerializer()
    sync_result = WalletSyncResultSerializer()


class PreparedEvmTransactionSerializer(serializers.Serializer):
    nonce = serializers.IntegerField()
    to = serializers.CharField()
    value = serializers.IntegerField()
    gas = serializers.IntegerField()
    gasPrice = serializers.IntegerField()
    chainId = serializers.IntegerField()
    data = serializers.CharField(required=False)


class PrepareWalletTransferSerializer(serializers.Serializer):
    to_address = serializers.CharField()
    amount_eth = serializers.CharField(required=False)
    amount_btc = serializers.CharField(required=False)
    amount_token = serializers.CharField(required=False)
    token_contract = serializers.CharField(required=False)


class PreparedEvmTransferSerializer(serializers.Serializer):
    transaction = PreparedEvmTransactionSerializer()
    gas_price_wei = serializers.CharField()
    gas_price_gwei = serializers.CharField()
    gas_limit = serializers.IntegerField()
    gas_cost_eth = serializers.CharField()
    from_address = serializers.CharField()
    to_address = serializers.CharField()
    amount_eth = serializers.CharField(required=False)
    total_cost_eth = serializers.CharField(required=False)
    amount_token = serializers.CharField(required=False)
    token_symbol = serializers.CharField(required=False)
    token_decimals = serializers.IntegerField(required=False)
    token_contract = serializers.CharField(required=False)


class PreparedBitcoinTransferSerializer(serializers.Serializer):
    from_address = serializers.CharField()
    to_address = serializers.CharField()
    amount_btc = serializers.CharField()
    amount_satoshis = serializers.IntegerField()
    fee_per_byte = serializers.CharField()
    estimated_tx_size = serializers.IntegerField()
    fee_satoshis = serializers.IntegerField()
    fee_btc = serializers.CharField()
    total_cost_btc = serializers.CharField()
    network = serializers.ChoiceField(choices=("BTC",))


class PendingTransferSerializer(serializers.Serializer):
    transaction_id = serializers.UUIDField()
    tx_hash = serializers.CharField()
    status = serializers.CharField()
    holding_quantity = serializers.CharField()


class BroadcastTransferResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    tx_hash = serializers.CharField()
    status = serializers.ChoiceField(choices=("pending", "confirmed", "failed", "reorged", "replaced"))
    message = serializers.CharField()
    pending_transaction = PendingTransferSerializer(allow_null=True)


class BatchBalanceResponseSerializer(serializers.Serializer):
    balances = serializers.DictField(child=serializers.CharField())
    errors = serializers.ListField(child=serializers.CharField(), required=False)


class BatchBalanceRequestSerializer(serializers.Serializer):
    addresses = serializers.ListField(child=serializers.CharField(), min_length=1, max_length=20)
    chain = serializers.ChoiceField(choices=sorted(SUPPORTED_CHAINS), default="ethereum")
