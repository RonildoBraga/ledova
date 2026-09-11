from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiResponse,
    PolymorphicProxySerializer,
    extend_schema_field,
)
from rest_framework import serializers

from shared.utils.typed_data import build_domain
from tokens.constants import MAX_ORDER_ACTION_QUANTITY
from tokens.models import (
    OrderActionPurpose,
    OrderActionStatus,
    ShareToken,
    TransferOrderStatus,
    TransferOrderType,
)
from tokens.serializers.order_submission import SubmissionOrderSerializer


class ActionQuantityField(serializers.RegexField):
    def __init__(self, *, positive=False, **kwargs):
        super().__init__(r"^[1-9][0-9]*$" if positive else r"^(0|[1-9][0-9]*)$", max_length=19, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Provide the exact quantity as a decimal string.")
        return super().to_internal_value(data)

    def run_validators(self, value):
        super().run_validators(value)
        if int(value) > MAX_ORDER_ACTION_QUANTITY:
            raise serializers.ValidationError("Quantity exceeds the supported order size.")


class ActionPriceField(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=18, decimal_places=2, min_value=Decimal("0.01"), **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Provide the exact price as a decimal string.")
        return super().to_internal_value(data)


class OrderActionIdentitySerializer(serializers.Serializer):
    action_id = serializers.UUIDField()
    owner_account_uuid = serializers.UUIDField()


class OrderActionModifyRequestSerializer(OrderActionIdentitySerializer):
    new_quantity = ActionQuantityField(positive=True)
    new_min_quantity = ActionQuantityField()
    new_price_per_share = ActionPriceField()

    def validate_new_quantity(self, value):
        return int(value)

    def validate_new_min_quantity(self, value):
        return int(value)


class OrderActionExecuteRequestSerializer(OrderActionIdentitySerializer):
    digest = serializers.CharField(required=False)
    signature = serializers.CharField(required=False)


class OrderActionLookupSerializer(serializers.Serializer):
    owner_account_uuid = serializers.UUIDField()


class OrderActionDomainSerializer(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField()
    chain_id = serializers.IntegerField(source="chainId")
    verifying_contract = serializers.CharField(source="verifyingContract")


class OrderActionTokenSerializer(serializers.Serializer):
    name = serializers.CharField()
    symbol = serializers.CharField()
    contract_address = serializers.CharField()


class OrderActionValuesSerializer(serializers.Serializer):
    quantity = serializers.RegexField(r"^[1-9][0-9]*$")
    min_quantity = serializers.RegexField(r"^(0|[1-9][0-9]*)$")
    price_per_share = serializers.DecimalField(max_digits=18, decimal_places=2)


class OrderActionCurrentValuesSerializer(OrderActionValuesSerializer):
    order_type = serializers.ChoiceField(choices=TransferOrderType.choices)
    status = serializers.ChoiceField(choices=TransferOrderStatus.choices)
    modification_count = serializers.IntegerField()
    filled_quantity = serializers.RegexField(r"^(0|[1-9][0-9]*)$")
    remaining_quantity = serializers.RegexField(r"^(0|[1-9][0-9]*)$")
    can_cancel = serializers.BooleanField()
    can_modify = serializers.BooleanField()


class OrderActionContextSerializer(serializers.Serializer):
    protocol_version = serializers.IntegerField()
    owner_account_uuid = serializers.UUIDField()
    order_uuid = serializers.UUIDField()
    wallet_uuid = serializers.UUIDField()
    token_uuid = serializers.UUIDField()
    wallet_address = serializers.CharField()
    domain = OrderActionDomainSerializer()
    token = OrderActionTokenSerializer()
    current_values = OrderActionCurrentValuesSerializer()


class OrderActionIntentSerializer(serializers.Serializer):
    domain = OrderActionDomainSerializer()
    modifications = OrderActionValuesSerializer(allow_null=True)


class OrderActionReviewSerializer(serializers.Serializer):
    token = OrderActionTokenSerializer()
    current_values = OrderActionCurrentValuesSerializer()


class OrderActionChangeSerializer(serializers.Serializer):
    field = serializers.ChoiceField(choices=["quantity", "min_quantity", "price_per_share"])
    old = serializers.CharField()
    new = serializers.CharField()


class OrderActionCancelResultSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["cancel"])
    from_status = serializers.ChoiceField(choices=TransferOrderStatus.choices)
    to_status = serializers.ChoiceField(choices=["cancelled"])


class OrderActionModifyResultSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["modify"])
    modification_count = serializers.IntegerField()
    changes = OrderActionChangeSerializer(many=True)


class OrderActionRefusalSerializer(serializers.Serializer):
    code = serializers.ChoiceField(
        choices=["order_cancellation_failed", "order_modification_failed", "order_modification_conflict"]
    )
    detail = serializers.CharField()
    http_status = serializers.ChoiceField(choices=[400, 409])


class OrderActionChallengeSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=["order_cancel", "order_modify"])
    digest = serializers.CharField()
    domain = OrderActionDomainSerializer()
    types = serializers.JSONField()
    message = serializers.JSONField()
    expires_at = serializers.DateTimeField()


class OrderActionSubmissionSerializer(serializers.Serializer):
    protocol_version = serializers.IntegerField()
    action_id = serializers.UUIDField()
    owner_account_uuid = serializers.UUIDField()
    order_uuid = serializers.UUIDField()
    wallet_uuid = serializers.UUIDField()
    token_uuid = serializers.UUIDField()
    wallet_address = serializers.CharField()
    purpose = serializers.ChoiceField(choices=OrderActionPurpose.choices)
    status = serializers.ChoiceField(choices=OrderActionStatus.choices)
    intent = OrderActionIntentSerializer()
    review = OrderActionReviewSerializer()
    order = SubmissionOrderSerializer()
    result = serializers.SerializerMethodField()
    refusal = OrderActionRefusalSerializer(allow_null=True)
    challenge = OrderActionChallengeSerializer(allow_null=True)

    @extend_schema_field(
        PolymorphicProxySerializer(
            component_name="OrderActionAppliedResult",
            serializers={
                "cancel": OrderActionCancelResultSerializer,
                "modify": OrderActionModifyResultSerializer,
            },
            resource_type_field_name="kind",
            allow_null=True,
        )
    )
    def get_result(self, value):
        return value["result"]


ORDER_ACTION_RESPONSES = {
    200: OrderActionSubmissionSerializer,
    400: OpenApiResponse(
        response={
            "anyOf": [
                {"$ref": "#/components/schemas/OrderActionSubmission"},
                {"type": "object", "additionalProperties": {}},
            ]
        },
        description="Recorded action refusal or ordinary pending request/challenge error.",
    ),
    401: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Authentication required."),
    403: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Signature refused."),
    404: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Unknown or currently inaccessible action/order."),
    409: OpenApiResponse(
        response={
            "anyOf": [
                {"$ref": "#/components/schemas/OrderActionSubmission"},
                {"type": "object", "additionalProperties": {}},
            ]
        },
        description="Recorded modification refusal or ordinary unresolved intent/context conflict.",
    ),
    429: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Request throttle exceeded."),
    500: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Unknown outcome; retain the action identity."),
    503: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Service unavailable; recover before retrying."),
}


def action_snapshot(action, challenge=None):
    token_metadata = ShareToken.objects.filter(pk=action.token_id).values("name", "symbol", "contract_address").first()
    if token_metadata is None:
        token_metadata = {**action.token_metadata, "contract_address": action.verifying_contract}
    return {
        "protocol_version": action.protocol_version,
        "action_id": str(action.action_id),
        "owner_account_uuid": str(action.owner_account_id),
        "order_uuid": str(action.order_id),
        "wallet_uuid": str(action.wallet_id),
        "token_uuid": str(action.token_id),
        "wallet_address": action.wallet_address,
        "purpose": action.purpose,
        "status": action.status,
        "intent": {
            "domain": build_domain(action.chain_id, action.verifying_contract),
            "modifications": (
                {
                    "quantity": str(action.new_quantity),
                    "min_quantity": str(action.new_min_quantity),
                    "price_per_share": str(action.new_price_per_share),
                }
                if action.purpose == OrderActionPurpose.MODIFY
                else None
            ),
        },
        "review": {
            "token": {**action.token_metadata, "contract_address": action.verifying_contract},
            "current_values": action.review_values,
        },
        "order": SubmissionOrderSerializer(action.order, context={"token_metadata": token_metadata}).data,
        "result": action.result,
        "refusal": (
            {"code": action.refusal_code, "detail": action.refusal_detail, "http_status": action.refusal_status}
            if action.status == OrderActionStatus.REFUSED
            else None
        ),
        "challenge": challenge,
    }
