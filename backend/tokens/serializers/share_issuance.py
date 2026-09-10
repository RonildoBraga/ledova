from rest_framework import serializers

from tokens.models import ShareIssuance


class ShareIssuanceListSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    issuance_type_display = serializers.CharField(source="get_issuance_type_display", read_only=True)
    initiated_by_email = serializers.EmailField(source="initiated_by.email", read_only=True, allow_null=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    subscription_reference = serializers.SerializerMethodField()

    class Meta:
        model = ShareIssuance
        fields = [
            "uuid",
            "token",
            "token_symbol",
            "subscription_reference",
            "recipient_address",
            "recipient_name",
            "amount",
            "issuance_type",
            "issuance_type_display",
            "reason",
            "status",
            "status_display",
            "tx_hash",
            "block_number",
            "initiated_by",
            "initiated_by_email",
            "processed_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_subscription_reference(self, issuance) -> str | None:
        request = getattr(issuance, "shareissuancerequest", None)
        subscription = None if request is None else getattr(request, "subscription", None)
        return None if subscription is None else (subscription.reference or str(subscription.uuid))
