from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


@extend_schema_field({"oneOf": [{"type": "number", "nullable": True}, {"type": "string"}, {"type": "boolean"}]})
class FiatPurchaseAmountField(serializers.JSONField):
    pass


class FiatPurchaseWidgetRequestSerializer(serializers.Serializer):
    wallet_uuid = serializers.CharField()
    crypto_currency_code = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    fiat_currency = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    default_fiat_currency = serializers.CharField(default="AUD", allow_null=True, allow_blank=True)
    fiat_amount = FiatPurchaseAmountField(required=False, allow_null=True)
    default_fiat_amount = FiatPurchaseAmountField(required=False, allow_null=True)
    theme_color = serializers.JSONField(required=False, allow_null=True)
    redirect_url = serializers.JSONField(required=False, allow_null=True)
