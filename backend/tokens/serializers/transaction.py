from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from tokens.models import MintRequest, ShareIssuance, SwapOrder


class AuthorizedWalletContextMixin:
    def _get_wallet_addresses(self) -> list[str]:
        return [address.lower() for address in self.context.get("authorized_wallet_addresses", ())]

    def _get_wallet_address(self, obj, *address_fields: str) -> str:
        authorized_addresses = {
            address.lower(): address for address in self.context.get("authorized_wallet_addresses", ())
        }
        for address_field in address_fields:
            candidate = getattr(obj, address_field, "")
            if candidate and candidate.lower() in authorized_addresses:
                return authorized_addresses[candidate.lower()]
        return ""


class SwapShareTransactionSerializer(AuthorizedWalletContextMixin, serializers.ModelSerializer):

    txHash = serializers.CharField(source="tx_hash", read_only=True)
    chain = serializers.SerializerMethodField()
    fromAddress = serializers.CharField(source="seller_address", read_only=True)
    toAddress = serializers.CharField(source="buyer_address", read_only=True)
    asset = serializers.CharField(source="share_token.symbol", read_only=True)
    assetSymbol = serializers.CharField(source="share_token.symbol", read_only=True)
    assetName = serializers.CharField(source="share_token.name", read_only=True)
    amount = serializers.CharField(source="share_amount", read_only=True)
    marketValue = serializers.SerializerMethodField()
    blockTimestamp = serializers.DateTimeField(source="completed_at", read_only=True)
    status = serializers.SerializerMethodField()
    transactionFee = serializers.SerializerMethodField()
    wallet = serializers.SerializerMethodField()
    walletAddress = serializers.SerializerMethodField()

    orderType = serializers.SerializerMethodField()
    pricePerShare = serializers.SerializerMethodField()
    paymentToken = serializers.CharField(source="payment_token.symbol", read_only=True)
    transactionType = serializers.SerializerMethodField()
    relatedSwapUuid = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = SwapOrder
        fields = [
            "uuid",
            "txHash",
            "chain",
            "fromAddress",
            "toAddress",
            "asset",
            "assetSymbol",
            "assetName",
            "amount",
            "marketValue",
            "blockTimestamp",
            "status",
            "transactionFee",
            "wallet",
            "walletAddress",
            "orderType",
            "pricePerShare",
            "paymentToken",
            "transactionType",
            "relatedSwapUuid",
        ]
        read_only_fields = fields

    def get_chain(self, obj: SwapOrder) -> str:
        return "ledova"

    def get_marketValue(self, obj: SwapOrder) -> str:
        decimals = obj.payment_token.decimals if obj.payment_token else 2
        divisor = Decimal(10) ** decimals
        return str(obj.payment_amount / divisor)

    def get_status(self, obj: SwapOrder) -> str:
        return "success" if obj.status == "completed" else obj.status

    def get_transactionFee(self, obj: SwapOrder) -> str:
        return "0"

    def get_wallet(self, obj: SwapOrder) -> str:
        return self._get_wallet_address(obj, "seller_address", "buyer_address")

    def get_walletAddress(self, obj: SwapOrder) -> str:
        return self._get_wallet_address(obj, "seller_address", "buyer_address")

    def get_orderType(self, obj: SwapOrder) -> str:
        if self._get_wallet_address(obj, "seller_address"):
            return "SELL"
        return "BUY"

    def get_pricePerShare(self, obj: SwapOrder) -> str:
        if obj.share_amount == 0:
            return "0"
        decimals = obj.payment_token.decimals if obj.payment_token else 2
        divisor = Decimal(10) ** decimals
        payment_value = Decimal(obj.payment_amount) / divisor
        price = payment_value / Decimal(obj.share_amount)
        return str(price.quantize(Decimal("0.01")))

    def get_transactionType(self, obj: SwapOrder) -> str:
        return "trade"


class SwapPaymentTransactionSerializer(AuthorizedWalletContextMixin, serializers.ModelSerializer):

    txHash = serializers.CharField(source="tx_hash", read_only=True)
    chain = serializers.SerializerMethodField()
    fromAddress = serializers.CharField(source="buyer_address", read_only=True)
    toAddress = serializers.CharField(source="seller_address", read_only=True)
    asset = serializers.CharField(source="payment_token.symbol", read_only=True)
    assetSymbol = serializers.CharField(source="payment_token.symbol", read_only=True)
    assetName = serializers.CharField(source="payment_token.name", read_only=True)
    amount = serializers.SerializerMethodField()
    marketValue = serializers.SerializerMethodField()
    blockTimestamp = serializers.DateTimeField(source="completed_at", read_only=True)
    status = serializers.SerializerMethodField()
    transactionFee = serializers.SerializerMethodField()
    wallet = serializers.SerializerMethodField()
    walletAddress = serializers.SerializerMethodField()

    orderType = serializers.SerializerMethodField()
    pricePerShare = serializers.SerializerMethodField()
    paymentToken = serializers.SerializerMethodField()
    transactionType = serializers.SerializerMethodField()
    relatedSwapUuid = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = SwapOrder
        fields = [
            "uuid",
            "txHash",
            "chain",
            "fromAddress",
            "toAddress",
            "asset",
            "assetSymbol",
            "assetName",
            "amount",
            "marketValue",
            "blockTimestamp",
            "status",
            "transactionFee",
            "wallet",
            "walletAddress",
            "orderType",
            "pricePerShare",
            "paymentToken",
            "transactionType",
            "relatedSwapUuid",
        ]
        read_only_fields = fields

    def get_chain(self, obj: SwapOrder) -> str:
        return "ledova"

    def get_amount(self, obj: SwapOrder) -> str:
        decimals = obj.payment_token.decimals if obj.payment_token else 2
        divisor = Decimal(10) ** decimals
        return str(obj.payment_amount / divisor)

    def get_marketValue(self, obj: SwapOrder) -> str:
        return self.get_amount(obj)

    def get_status(self, obj: SwapOrder) -> str:
        return "success" if obj.status == "completed" else obj.status

    def get_transactionFee(self, obj: SwapOrder) -> str:
        return "0"

    def get_wallet(self, obj: SwapOrder) -> str:
        return self._get_wallet_address(obj, "buyer_address", "seller_address")

    def get_walletAddress(self, obj: SwapOrder) -> str:
        return self._get_wallet_address(obj, "buyer_address", "seller_address")

    def get_orderType(self, obj: SwapOrder) -> str:
        if self._get_wallet_address(obj, "buyer_address"):
            return "PAYMENT_SENT"
        return "PAYMENT_RECEIVED"

    def get_pricePerShare(self, obj: SwapOrder) -> str:
        return None

    def get_paymentToken(self, obj: SwapOrder) -> str:
        return None

    def get_transactionType(self, obj: SwapOrder) -> str:
        return "swap_payment"


class MintTransactionSerializer(AuthorizedWalletContextMixin, serializers.ModelSerializer):

    txHash = serializers.CharField(source="transaction.tx_hash", read_only=True)
    chain = serializers.SerializerMethodField()
    fromAddress = serializers.SerializerMethodField()
    toAddress = serializers.CharField(source="recipient_address", read_only=True)
    asset = serializers.SerializerMethodField()
    assetSymbol = serializers.SerializerMethodField()
    assetName = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    marketValue = serializers.SerializerMethodField()
    blockTimestamp = serializers.DateTimeField(source="executed_at", read_only=True)
    status = serializers.SerializerMethodField()
    transactionFee = serializers.SerializerMethodField()
    wallet = serializers.SerializerMethodField()
    walletAddress = serializers.SerializerMethodField()

    orderType = serializers.SerializerMethodField()
    pricePerShare = serializers.SerializerMethodField()
    paymentToken = serializers.SerializerMethodField()
    transactionType = serializers.SerializerMethodField()

    class Meta:
        model = MintRequest
        fields = [
            "uuid",
            "txHash",
            "chain",
            "fromAddress",
            "toAddress",
            "asset",
            "assetSymbol",
            "assetName",
            "amount",
            "marketValue",
            "blockTimestamp",
            "status",
            "transactionFee",
            "wallet",
            "walletAddress",
            "orderType",
            "pricePerShare",
            "paymentToken",
            "transactionType",
        ]
        read_only_fields = fields

    def get_chain(self, obj: MintRequest) -> str:
        return "ledova"

    def get_fromAddress(self, obj: MintRequest) -> str:
        if obj.transaction and obj.transaction.from_address:
            return obj.transaction.from_address
        return getattr(settings, "LEDOVA_SIGNER_ADDRESS", "0x0000000000000000000000000000000000000000")

    def get_asset(self, obj: MintRequest) -> str:
        token = obj.token
        return token.symbol if token else ""

    def get_assetSymbol(self, obj: MintRequest) -> str:
        token = obj.token
        return token.symbol if token else ""

    def get_assetName(self, obj: MintRequest) -> str:
        token = obj.token
        return token.name if token else ""

    def get_amount(self, obj: MintRequest) -> str:
        token = obj.token
        decimals = token.decimals if token else 2
        divisor = Decimal(10) ** decimals
        return str(Decimal(obj.amount) / divisor)

    def get_marketValue(self, obj: MintRequest) -> str:
        return self.get_amount(obj)

    def get_status(self, obj: MintRequest) -> str:
        return "success" if obj.status == "executed" else obj.status

    def get_transactionFee(self, obj: MintRequest) -> str:
        return "0"

    def get_wallet(self, obj: MintRequest) -> str:
        return self._get_wallet_address(obj, "recipient_address")

    def get_walletAddress(self, obj: MintRequest) -> str:
        return self._get_wallet_address(obj, "recipient_address")

    def get_orderType(self, obj: MintRequest) -> str:
        return "MINT"

    def get_pricePerShare(self, obj: MintRequest) -> str:
        return None

    def get_paymentToken(self, obj: MintRequest) -> str:
        return None

    def get_transactionType(self, obj: MintRequest) -> str:
        if obj.stablecoin_id:
            return "stablecoin_mint"
        return "yield_token_mint"


class ShareIssuanceTransactionSerializer(AuthorizedWalletContextMixin, serializers.ModelSerializer):

    txHash = serializers.CharField(source="tx_hash", read_only=True)
    chain = serializers.SerializerMethodField()
    fromAddress = serializers.SerializerMethodField()
    toAddress = serializers.CharField(source="recipient_address", read_only=True)
    asset = serializers.CharField(source="token.symbol", read_only=True)
    assetSymbol = serializers.CharField(source="token.symbol", read_only=True)
    assetName = serializers.CharField(source="token.name", read_only=True)
    amount = serializers.CharField(read_only=True)
    marketValue = serializers.SerializerMethodField()
    blockTimestamp = serializers.DateTimeField(source="completed_at", read_only=True)
    status = serializers.SerializerMethodField()
    transactionFee = serializers.SerializerMethodField()
    wallet = serializers.SerializerMethodField()
    walletAddress = serializers.SerializerMethodField()

    orderType = serializers.SerializerMethodField()
    pricePerShare = serializers.SerializerMethodField()
    paymentToken = serializers.SerializerMethodField()
    transactionType = serializers.SerializerMethodField()
    issuanceType = serializers.CharField(source="issuance_type", read_only=True)

    class Meta:
        model = ShareIssuance
        fields = [
            "uuid",
            "txHash",
            "chain",
            "fromAddress",
            "toAddress",
            "asset",
            "assetSymbol",
            "assetName",
            "amount",
            "marketValue",
            "blockTimestamp",
            "status",
            "transactionFee",
            "wallet",
            "walletAddress",
            "orderType",
            "pricePerShare",
            "paymentToken",
            "transactionType",
            "issuanceType",
        ]
        read_only_fields = fields

    def get_chain(self, obj: ShareIssuance) -> str:
        return "ledova"

    def get_fromAddress(self, obj: ShareIssuance) -> str:
        if obj.token and obj.token.contract_address:
            return obj.token.contract_address
        return getattr(settings, "LEDOVA_SIGNER_ADDRESS", "0x0000000000000000000000000000000000000000")

    def get_marketValue(self, obj: ShareIssuance) -> str:
        return "0"

    def get_status(self, obj: ShareIssuance) -> str:
        return "success" if obj.status == "completed" else obj.status

    def get_transactionFee(self, obj: ShareIssuance) -> str:
        return "0"

    def get_wallet(self, obj: ShareIssuance) -> str:
        return self._get_wallet_address(obj, "recipient_address")

    def get_walletAddress(self, obj: ShareIssuance) -> str:
        return self._get_wallet_address(obj, "recipient_address")

    def get_orderType(self, obj: ShareIssuance) -> str:
        return "ISSUANCE"

    def get_pricePerShare(self, obj: ShareIssuance) -> str:
        return None

    def get_paymentToken(self, obj: ShareIssuance) -> str:
        return None

    def get_transactionType(self, obj: ShareIssuance) -> str:
        return "token_issuance"
