from rest_framework import serializers

from tokens.models import ShareIssuanceRequest


class ShareIssuanceRequestSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    issuance_type_display = serializers.CharField(source="get_issuance_type_display", read_only=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    token_name = serializers.CharField(source="token.name", read_only=True)
    submitted_by_email = serializers.EmailField(source="submitted_by.email", read_only=True, allow_null=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True, allow_null=True)

    class Meta:
        model = ShareIssuanceRequest
        fields = [
            "uuid",
            "token",
            "token_symbol",
            "token_name",
            "recipient_address",
            "recipient_name",
            "amount",
            "issuance_type",
            "issuance_type_display",
            "reason",
            "status",
            "status_display",
            "dilution_percentage",
            "submitted_by",
            "submitted_by_email",
            "submitted_at",
            "reviewed_by",
            "reviewed_by_email",
            "reviewed_at",
            "review_notes",
            "rejection_reason",
            "executed_issuance",
            "executed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
