from rest_framework import serializers

from tokens.models import OrderSubmissionStatus, ShareToken
from tokens.serializers.transfer_order import (
    TransferOrderCreateSerializer,
    TransferOrderDetailSerializer,
)


class SignedOrderSubmissionSerializer(TransferOrderCreateSerializer):
    digest = serializers.CharField(required=False, allow_blank=True)
    signature = serializers.CharField(required=False, allow_blank=True)


class OrderSubmissionLookupSerializer(serializers.Serializer):
    owner_account_uuid = serializers.UUIDField()


class OrderSubmissionIntentSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    order_type = serializers.ChoiceField(choices=["buy", "sell"])
    wallet_address = serializers.CharField()
    quantity = serializers.RegexField(r"^[1-9][0-9]*$")
    min_quantity = serializers.RegexField(r"^(0|[1-9][0-9]*)$")
    price_per_share = serializers.DecimalField(max_digits=18, decimal_places=2)


class OrderSubmissionMatchSerializer(serializers.Serializer):
    matched = serializers.BooleanField()
    counter_order = serializers.UUIDField()
    swap_order = serializers.UUIDField()


class OrderSubmissionRefusalSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()


class OrderCreateChallengeSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=["order_create"])
    token_uuid = serializers.UUIDField()
    wallet_address = serializers.CharField()
    digest = serializers.CharField()
    domain = serializers.JSONField()
    types = serializers.JSONField()
    message = serializers.JSONField()
    expires_at = serializers.DateTimeField()


class SubmissionOrderSerializer(TransferOrderDetailSerializer):
    token_symbol = serializers.SerializerMethodField()
    token_name = serializers.SerializerMethodField()
    token_contract_address = serializers.SerializerMethodField()

    def get_token_symbol(self, order) -> str:
        return self.context["token_metadata"]["symbol"]

    def get_token_name(self, order) -> str:
        return self.context["token_metadata"]["name"]

    def get_token_contract_address(self, order) -> str:
        return self.context["token_metadata"]["contract_address"]


class OrderSubmissionSerializer(serializers.Serializer):
    submission_id = serializers.UUIDField()
    owner_account_uuid = serializers.UUIDField()
    wallet_uuid = serializers.UUIDField()
    status = serializers.ChoiceField(choices=OrderSubmissionStatus.choices)
    intent = OrderSubmissionIntentSerializer()
    order = SubmissionOrderSerializer(allow_null=True)
    match = OrderSubmissionMatchSerializer(allow_null=True)
    refusal = OrderSubmissionRefusalSerializer(allow_null=True)
    challenge = OrderCreateChallengeSerializer(allow_null=True)


def submission_snapshot(submission, challenge=None):
    order_data = None
    if submission.order_id is not None:
        token_metadata = (
            ShareToken.objects.filter(pk=submission.token_id).values("name", "symbol", "contract_address").first()
        )
        if token_metadata is None:
            token_metadata = {**submission.token_metadata, "contract_address": submission.verifying_contract}
        order_data = SubmissionOrderSerializer(submission.order, context={"token_metadata": token_metadata}).data
    return {
        "submission_id": str(submission.submission_id),
        "owner_account_uuid": str(submission.owner_account_id),
        "wallet_uuid": str(submission.wallet_id),
        "status": submission.status,
        "intent": {
            "token": str(submission.token_id),
            "order_type": submission.order_type,
            "wallet_address": submission.wallet_address,
            "quantity": str(submission.quantity),
            "min_quantity": str(submission.min_quantity),
            "price_per_share": str(submission.price_per_share),
        },
        "order": order_data,
        "match": (
            {
                "matched": True,
                "counter_order": str(submission.initial_counter_order_id),
                "swap_order": str(submission.initial_swap_id),
            }
            if submission.initial_swap_id is not None
            else None
        ),
        "refusal": (
            {"code": submission.refusal_code, "detail": submission.refusal_detail}
            if submission.status == OrderSubmissionStatus.REFUSED
            else None
        ),
        "challenge": challenge,
    }
