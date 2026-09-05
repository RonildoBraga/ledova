from rest_framework import serializers

from assets.models import Asset
from companies.models import CompanyDocument
from offerings.models import Offering
from operators.settlement import settlement_assets
from tokens.models import ShareToken

WRITABLE_FIELDS = [
    "token",
    "exemption",
    "price_per_share",
    "price_currency",
    "settlement_assets",
    "accepts_bank_transfer",
    "minimum_shares",
    "target_shares",
    "cap_shares",
    "maximum_shares",
    "opens_at",
    "closes_at",
    "summary",
    "use_of_proceeds",
    "documents",
]

NOT_EDITABLE = "Only a draft offering can be edited."
BOUNDS_ORDER = "Order the bounds minimum <= target <= cap."
WINDOW_ORDER = "An offering must close after it opens."
MAXIMUM_ORDER = "The maximum per investor must be at least the minimum."


class OfferingListSerializer(serializers.ModelSerializer):

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    exemption_display = serializers.CharField(source="get_exemption_display", read_only=True)
    token_uuid = serializers.UUIDField(source="token.uuid", read_only=True)
    token_symbol = serializers.CharField(source="token.symbol", read_only=True)
    token_name = serializers.CharField(source="token.name", read_only=True)

    class Meta:
        model = Offering
        fields = [
            "uuid",
            "token_uuid",
            "token_symbol",
            "token_name",
            "status",
            "status_display",
            "exemption",
            "exemption_display",
            "price_per_share",
            "price_currency",
            "minimum_shares",
            "target_shares",
            "cap_shares",
            "maximum_shares",
            "opens_at",
            "closes_at",
            "is_open",
            "created_at",
        ]
        read_only_fields = fields


class OfferingDetailSerializer(OfferingListSerializer):

    settlement_assets = serializers.SlugRelatedField(slug_field="uuid", many=True, read_only=True)
    documents = serializers.SlugRelatedField(slug_field="uuid", many=True, read_only=True)
    submitted_by_email = serializers.EmailField(source="submitted_by.email", read_only=True, allow_null=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True, allow_null=True)
    can_be_edited = serializers.BooleanField(read_only=True)

    class Meta(OfferingListSerializer.Meta):
        fields = OfferingListSerializer.Meta.fields + [
            "settlement_assets",
            "accepts_bank_transfer",
            "summary",
            "use_of_proceeds",
            "documents",
            "submitted_by_email",
            "submitted_at",
            "reviewed_by_email",
            "reviewed_at",
            "review_notes",
            "rejection_reason",
            "closed_at",
            "close_reason",
            "can_be_edited",
            "updated_at",
        ]
        read_only_fields = fields


class OfferingWriteSerializer(serializers.ModelSerializer):

    token = serializers.SlugRelatedField(slug_field="uuid", queryset=ShareToken.objects.none())
    settlement_assets = serializers.SlugRelatedField(
        slug_field="uuid", many=True, required=False, queryset=Asset.objects.none()
    )
    documents = serializers.SlugRelatedField(
        slug_field="uuid", many=True, required=False, queryset=CompanyDocument.objects.none()
    )

    class Meta:
        model = Offering
        fields = WRITABLE_FIELDS

    def get_fields(self):
        fields = super().get_fields()
        user = getattr(self.context.get("request"), "user", None)
        fields["token"].queryset = ShareToken.objects.manageable_by_user(user)
        fields["settlement_assets"].child_relation.queryset = settlement_assets()
        fields["documents"].child_relation.queryset = CompanyDocument.objects.manageable_by_user(user)
        return fields

    def _value(self, attrs, name):
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name, None)

    def validate(self, attrs):
        if self.instance is not None and not self.instance.can_be_edited:
            raise serializers.ValidationError(NOT_EDITABLE)
        minimum = self._value(attrs, "minimum_shares")
        target = self._value(attrs, "target_shares")
        cap = self._value(attrs, "cap_shares")
        if minimum < 1 or target < minimum or cap < target:
            raise serializers.ValidationError({"cap_shares": BOUNDS_ORDER})
        maximum = self._value(attrs, "maximum_shares")
        if maximum is not None and maximum < minimum:
            raise serializers.ValidationError({"maximum_shares": MAXIMUM_ORDER})
        closes_at = self._value(attrs, "closes_at")
        if closes_at is not None and closes_at <= self._value(attrs, "opens_at"):
            raise serializers.ValidationError({"closes_at": WINDOW_ORDER})
        return attrs

    def validate_token(self, value):
        if self.instance is not None and value != self.instance.token:
            raise serializers.ValidationError("The share class of an offering cannot be changed.")
        return value

    def to_representation(self, instance):
        return OfferingDetailSerializer(instance, context=self.context).data


class OfferingWithdrawSerializer(serializers.Serializer):

    reason = serializers.CharField(required=False, allow_blank=True)
