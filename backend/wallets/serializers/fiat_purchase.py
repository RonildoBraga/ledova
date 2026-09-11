from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


@extend_schema_field(
    {
        "oneOf": [
            {"type": "number", "nullable": True},
            {"type": "string"},
            {"type": "boolean"},
            {"type": "array", "items": {}, "maxItems": 0},
            {"type": "object", "maxProperties": 0},
        ]
    }
)
class FiatPurchaseAmountField(serializers.JSONField):
    pass


@extend_schema_field(
    {
        "oneOf": [
            {"type": "string", "nullable": True},
            {"type": "number", "enum": [0]},
            {"type": "boolean", "enum": [False]},
            {"type": "array", "items": {}, "maxItems": 0},
            {"type": "object", "maxProperties": 0},
        ]
    }
)
class FiatPurchaseCurrencyField(serializers.JSONField):
    pass


class FiatPurchaseWidgetRequestSerializer(serializers.Serializer):
    wallet_uuid = serializers.CharField()
    crypto_currency_code = FiatPurchaseCurrencyField(required=False, allow_null=True)
    fiat_currency = FiatPurchaseCurrencyField(required=False, allow_null=True)
    default_fiat_currency = FiatPurchaseCurrencyField(default="AUD", allow_null=True)
    fiat_amount = FiatPurchaseAmountField(required=False, allow_null=True)
    default_fiat_amount = FiatPurchaseAmountField(required=False, allow_null=True)
    theme_color = serializers.JSONField(required=False, allow_null=True)
    redirect_url = serializers.JSONField(required=False, allow_null=True)
