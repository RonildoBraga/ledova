from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from companies.models import Company
from tokens.serializers import ShareTokenListSerializer

DIRECTORY_COMPANY_FIELDS = ["display_name", "industry", "city", "state"]


class DirectoryCompanySerializer(serializers.ModelSerializer):

    class Meta:
        model = Company
        fields = DIRECTORY_COMPANY_FIELDS
        read_only_fields = fields


class DirectoryOpenOfferingSerializer(serializers.Serializer):

    uuid = serializers.UUIDField(source="open_offering_uuid", read_only=True)
    price_per_share = serializers.DecimalField(
        source="open_offering_price", max_digits=18, decimal_places=2, read_only=True
    )
    price_currency = serializers.CharField(source="open_offering_currency", read_only=True)
    opens_at = serializers.DateTimeField(source="open_offering_opens_at", read_only=True)
    closes_at = serializers.DateTimeField(source="open_offering_closes_at", read_only=True)


class DirectoryOpenOfferingResponseSerializer(DirectoryOpenOfferingSerializer):
    closes_at = serializers.DateTimeField(source="open_offering_closes_at", read_only=True, allow_null=True)


class DirectoryTokenListSerializer(ShareTokenListSerializer):

    company = DirectoryCompanySerializer(read_only=True)
    issued_shares = serializers.IntegerField(read_only=True)
    open_offering = serializers.SerializerMethodField()

    class Meta(ShareTokenListSerializer.Meta):
        fields = ShareTokenListSerializer.Meta.fields + ["issued_shares", "open_offering"]
        read_only_fields = fields

    @extend_schema_field(DirectoryOpenOfferingResponseSerializer(allow_null=True))
    def get_open_offering(self, obj):
        if obj.open_offering_uuid is None:
            return None
        return DirectoryOpenOfferingSerializer(obj).data
