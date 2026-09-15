from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


class SigningDomainSerializer(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField()
    chain_id = serializers.IntegerField(source="chainId")
    verifying_contract = serializers.CharField(source="verifyingContract")


@extend_schema_field(SigningDomainSerializer)
class SigningDomainField(serializers.JSONField):
    pass


@extend_schema_field(
    {
        "type": "object",
        "additionalProperties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "type": {"type": "string"}},
                "required": ["name", "type"],
            },
        },
    },
    component_name="SigningTypes",
)
class SigningTypesField(serializers.JSONField):
    pass


@extend_schema_field(serializers.DictField(child=serializers.CharField()), component_name="SigningMessage")
class SigningMessageField(serializers.JSONField):
    pass


class SwapMessageSerializer(serializers.Serializer):
    seller = serializers.CharField()
    buyer = serializers.CharField()
    share_token = serializers.CharField()
    payment_token = serializers.CharField()
    share_amount = serializers.CharField()
    payment_amount = serializers.CharField()
    nonce = serializers.CharField()
    deadline = serializers.CharField()


class SigningTypeSerializer(serializers.Serializer):
    name = serializers.CharField()
    type = serializers.CharField()


class SwapSigningTypesSerializer(serializers.Serializer):
    EIP712Domain = SigningTypeSerializer(many=True)
    SwapOrder = SigningTypeSerializer(many=True)


@extend_schema_field(SwapSigningTypesSerializer)
class SwapSigningTypesField(serializers.JSONField):
    pass


class SettlementDomainSerializer(SigningDomainSerializer):
    name = serializers.ChoiceField(choices=["LedovaAtomicSwap"])
    version = serializers.ChoiceField(choices=["1"])
    chain_id = serializers.CharField(source="chainId")


class SettlementTypedDataSerializer(serializers.Serializer):
    types = SwapSigningTypesField()
    primary_type = serializers.ChoiceField(choices=["SwapOrder"])
    domain = SettlementDomainSerializer()
    message = SwapMessageSerializer()


class SettlementPartySerializer(serializers.Serializer):
    order_uuid = serializers.UUIDField()
    owner_account_uuid = serializers.UUIDField()
    wallet_uuid = serializers.UUIDField()
    payment_asset_uuid = serializers.UUIDField(allow_null=True)
    address = serializers.CharField()


class SettlementShareTokenSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    address = serializers.CharField()
    chain = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    decimals = serializers.IntegerField()


class SettlementPaymentAssetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    pricing_decimals = serializers.IntegerField()
    deployment_uuid = serializers.UUIDField()
    deployment_chain = serializers.CharField()
    deployment_address = serializers.CharField()
    deployment_decimals = serializers.IntegerField()


class SettlementContextSerializer(serializers.Serializer):
    protocol_version = serializers.ChoiceField(choices=[1])
    swap_uuid = serializers.UUIDField()
    seller = SettlementPartySerializer()
    buyer = SettlementPartySerializer()
    share_token = SettlementShareTokenSerializer()
    payment_asset = SettlementPaymentAssetSerializer()
    price_per_share = serializers.CharField()
    typed_data = SettlementTypedDataSerializer()
    digest = serializers.CharField()
    order_hash = serializers.CharField()


@extend_schema_field(SettlementContextSerializer)
class SettlementContextField(serializers.JSONField):
    pass
