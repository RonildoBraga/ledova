from django.conf import settings
from rest_framework import serializers
from web3 import Web3

from tokens.models import (
    ShareToken,
    Stablecoin,
    TransferOrder,
    TransferOrderType,
)
from wallets.models import Wallet


class TransferOrderListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    order_type_display = serializers.CharField(source="get_order_type_display", read_only=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    token_name = serializers.CharField(source="token.name", read_only=True)
    total_value = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    remaining_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = TransferOrder
        fields = [
            "uuid",
            "token",
            "token_symbol",
            "token_name",
            "order_type",
            "order_type_display",
            "status",
            "status_display",
            "wallet_address",
            "quantity",
            "min_quantity",
            "filled_quantity",
            "remaining_quantity",
            "price_per_share",
            "total_value",
            "created_at",
        ]
        read_only_fields = fields


class TransferOrderDetailSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    order_type_display = serializers.CharField(source="get_order_type_display", read_only=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    token_name = serializers.CharField(source="token.name", read_only=True)
    token_contract_address = serializers.CharField(source="token.contract_address", read_only=True)
    total_value = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    remaining_quantity = serializers.IntegerField(read_only=True)
    remaining_value = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    matched_order_uuid = serializers.UUIDField(source="matched_order.uuid", read_only=True, allow_null=True)
    can_be_modified = serializers.BooleanField(read_only=True)

    class Meta:
        model = TransferOrder
        fields = [
            "uuid",
            "token",
            "token_symbol",
            "token_name",
            "token_contract_address",
            "order_type",
            "order_type_display",
            "status",
            "status_display",
            "wallet_address",
            "quantity",
            "min_quantity",
            "filled_quantity",
            "remaining_quantity",
            "price_per_share",
            "total_value",
            "remaining_value",
            "matched_order_uuid",
            "tx_hash",
            "completed_at",
            "error_message",
            "modification_count",
            "last_modified_at",
            "can_be_modified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TransferOrderCreateSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    order_type = serializers.ChoiceField(choices=TransferOrderType.choices)
    wallet_uuid = serializers.UUIDField(write_only=True)
    wallet_address = serializers.CharField(max_length=42)
    quantity = serializers.IntegerField(min_value=1)
    min_quantity = serializers.IntegerField(
        required=False,
        min_value=0,
        default=0,
        help_text="Minimum quantity per fill. 0 means accept any partial fill.",
    )
    price_per_share = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0.01)

    def validate_token(self, value):
        try:
            token = ShareToken.objects.get(uuid=value)
        except ShareToken.DoesNotExist:
            raise serializers.ValidationError("Token not found")

        if not token.is_deployed:
            raise serializers.ValidationError("Token is not deployed")

        return token

    def validate_wallet_address(self, value):
        if not Web3.is_address(value):
            raise serializers.ValidationError("Invalid Ethereum address format")
        return Web3.to_checksum_address(value)

    def validate(self, data):
        quantity = data.get("quantity", 0)
        min_quantity = data.get("min_quantity", 0)

        if min_quantity > quantity:
            raise serializers.ValidationError({"min_quantity": "Minimum quantity cannot exceed total quantity."})

        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            raise serializers.ValidationError({"wallet_uuid": "An authenticated wallet owner is required."})

        wallet = (
            Wallet.objects.visible_to_user(request.user)
            .verified_evm()
            .select_related("user_account")
            .filter(uuid=data["wallet_uuid"])
            .first()
        )

        if wallet is None:
            raise serializers.ValidationError(
                {"wallet_uuid": "Select a verified EVM wallet from one of your accounts."}
            )

        if not Web3.is_address(wallet.address):
            raise serializers.ValidationError({"wallet_uuid": "The selected wallet has an invalid EVM address."})

        canonical_wallet_address = Web3.to_checksum_address(wallet.address)
        if canonical_wallet_address != data["wallet_address"]:
            raise serializers.ValidationError(
                {"wallet_address": "The wallet address does not match the selected wallet."}
            )

        data["wallet"] = wallet
        data["owner_account"] = wallet.user_account
        data["wallet_address"] = canonical_wallet_address

        return data


class PrepareTransferSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    from_address = serializers.CharField(max_length=42)
    to_address = serializers.CharField(max_length=42)
    amount = serializers.IntegerField(min_value=1)

    def validate_token(self, value):
        token = ShareToken.objects.filter(uuid=value).first()
        if token:
            if not token.is_deployed:
                raise serializers.ValidationError("Token is not deployed")
            return token

        token = Stablecoin.objects.filter(uuid=value).first()
        if token:
            if not token.is_active:
                raise serializers.ValidationError("Stablecoin is not active")
            return token

        raise serializers.ValidationError("Token not found")

    def validate_from_address(self, value):
        if not value.startswith("0x") or len(value) != 42:
            raise serializers.ValidationError("Invalid Ethereum address format")
        return value

    def validate_to_address(self, value):
        if not value.startswith("0x") or len(value) != 42:
            raise serializers.ValidationError("Invalid Ethereum address format")
        return value


class BroadcastTransferSerializer(serializers.Serializer):

    signed_transaction = serializers.CharField()

    def validate_signed_transaction(self, value):
        if not value.startswith("0x"):
            raise serializers.ValidationError("Signed transaction must start with 0x")

        from tokens.services.contracts import known_contract_addresses
        from tokens.services.signed_transactions import decode_signed_transaction

        try:
            decoded = decode_signed_transaction(bytes.fromhex(value[2:]))
        except ValueError:
            raise serializers.ValidationError("Unable to decode signed transaction")

        if decoded.chain_id is not None and decoded.chain_id != settings.BLOCKCHAIN_CHAIN_ID:
            raise serializers.ValidationError("Transaction is signed for a different network")

        if decoded.to is None:
            raise serializers.ValidationError("Contract creation transactions are not allowed")

        if decoded.to.lower() not in known_contract_addresses():
            raise serializers.ValidationError("Transaction target is not a known Ledova contract")

        return value


class OrderModificationRequestSerializer(serializers.Serializer):

    new_quantity = serializers.IntegerField(required=False, min_value=1)
    new_min_quantity = serializers.IntegerField(required=False, min_value=0)
    new_price_per_share = serializers.DecimalField(required=False, max_digits=18, decimal_places=2, min_value=0.01)

    def validate(self, data):
        if not data:
            raise serializers.ValidationError("At least one modification field must be provided")
        return data


class OrderModificationExecuteSerializer(serializers.Serializer):

    message = serializers.CharField()
    signature = serializers.CharField()

    def validate_signature(self, value):
        if not value.startswith("0x"):
            raise serializers.ValidationError("Signature must start with 0x")
        if len(value) != 132:
            raise serializers.ValidationError("Invalid signature length")
        return value
