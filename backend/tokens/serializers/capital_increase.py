from rest_framework import serializers

from tokens.exceptions import InvalidTokenStateException
from tokens.models import CapitalIncreaseRequest, ShareTokenStatus


class CapitalIncreaseListSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    token_name = serializers.CharField(source="token.name", read_only=True)
    submitted_by_email = serializers.EmailField(source="submitted_by.email", read_only=True, allow_null=True)

    class Meta:
        model = CapitalIncreaseRequest
        fields = [
            "uuid",
            "token",
            "token_symbol",
            "token_name",
            "additional_shares",
            "new_authorized_total",
            "purpose",
            "status",
            "status_display",
            "dilution_percentage",
            "submitted_by",
            "submitted_by_email",
            "submitted_at",
            "created_at",
        ]
        read_only_fields = fields


class CapitalIncreaseDetailSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    token_name = serializers.CharField(source="token.name", read_only=True)
    submitted_by_email = serializers.EmailField(source="submitted_by.email", read_only=True, allow_null=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True, allow_null=True)

    can_be_edited = serializers.BooleanField(read_only=True)
    can_be_submitted = serializers.BooleanField(read_only=True)

    class Meta:
        model = CapitalIncreaseRequest
        fields = [
            "uuid",
            "token",
            "token_symbol",
            "token_name",
            "additional_shares",
            "new_authorized_total",
            "purpose",
            "board_resolution_reference",
            "shareholder_approval_reference",
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
            "can_be_edited",
            "can_be_submitted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CapitalIncreaseCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = CapitalIncreaseRequest
        fields = [
            "additional_shares",
            "new_authorized_total",
            "purpose",
            "board_resolution_reference",
            "shareholder_approval_reference",
        ]

    def validate_additional_shares(self, value):
        if value <= 0:
            raise serializers.ValidationError("Additional shares must be greater than zero")
        return value

    def validate_new_authorized_total(self, value):
        if value <= 0:
            raise serializers.ValidationError("New authorized total must be greater than zero")
        return value

    def validate(self, attrs):
        token = self.context["token"]
        if token.status != ShareTokenStatus.DEPLOYED:
            raise InvalidTokenStateException("Capital increase requests can only be created for deployed tokens.")

        additional = attrs["additional_shares"]
        current_supply = int(token.total_supply) if token.total_supply else 0
        expected_new_total = current_supply + additional
        if attrs["new_authorized_total"] < expected_new_total:
            raise serializers.ValidationError(
                {
                    "new_authorized_total": (
                        f"Must be at least current supply ({current_supply}) + "
                        f"additional shares ({additional}) = {expected_new_total}"
                    )
                }
            )
        return attrs


class CapitalIncreaseUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = CapitalIncreaseRequest
        fields = [
            "additional_shares",
            "new_authorized_total",
            "purpose",
            "board_resolution_reference",
            "shareholder_approval_reference",
        ]

    def validate_additional_shares(self, value):
        if value <= 0:
            raise serializers.ValidationError("Additional shares must be greater than zero")
        return value

    def validate_new_authorized_total(self, value):
        if value <= 0:
            raise serializers.ValidationError("New authorized total must be greater than zero")
        return value

    def validate(self, attrs):
        if not self.instance.can_be_edited:
            raise InvalidTokenStateException("Only draft requests can be edited.")

        additional = attrs.get("additional_shares", self.instance.additional_shares)
        new_total = attrs.get("new_authorized_total", self.instance.new_authorized_total)
        if new_total < additional:
            raise serializers.ValidationError("New authorized total must be at least equal to additional shares")
        return attrs

    def to_representation(self, instance):
        return CapitalIncreaseDetailSerializer(instance, context=self.context).data
