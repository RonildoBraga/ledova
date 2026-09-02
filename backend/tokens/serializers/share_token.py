from rest_framework import serializers

from companies.models import Company
from tokens.models import ShareToken


class ShareTokenListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    token_type_display = serializers.CharField(source="get_token_type_display", read_only=True)
    company_uuid = serializers.UUIDField(source="company.uuid", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    last_price = serializers.SerializerMethodField()
    best_bid = serializers.SerializerMethodField()
    best_ask = serializers.SerializerMethodField()

    class Meta:
        model = ShareToken
        fields = [
            "uuid",
            "company",
            "company_uuid",
            "company_name",
            "name",
            "symbol",
            "token_type",
            "token_type_display",
            "status",
            "status_display",
            "contract_address",
            "total_supply",
            "decimals",
            "is_transferable",
            "is_divisible",
            "deployed_at",
            "created_at",
            "last_price",
            "best_bid",
            "best_ask",
        ]
        read_only_fields = fields

    def get_last_price(self, obj):
        from tokens.services import MarketDataService

        last_trade = MarketDataService.get_last_trade(obj)
        if last_trade:
            return str(MarketDataService.calculate_trade_price(last_trade))
        return None

    def get_best_bid(self, obj):
        from tokens.models import TransferOrder

        best = TransferOrder.objects.best_bid(obj)
        return str(best.price_per_share) if best else None

    def get_best_ask(self, obj):
        from tokens.models import TransferOrder

        best = TransferOrder.objects.best_ask(obj)
        return str(best.price_per_share) if best else None


class ShareTokenDetailSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    token_type_display = serializers.CharField(source="get_token_type_display", read_only=True)
    company_uuid = serializers.UUIDField(source="company.uuid", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = ShareToken
        fields = [
            "uuid",
            "company",
            "company_uuid",
            "company_name",
            "name",
            "symbol",
            "token_type",
            "token_type_display",
            "status",
            "status_display",
            "contract_address",
            "total_supply",
            "decimals",
            "is_transferable",
            "is_divisible",
            "deployment_tx_hash",
            "deployed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ShareTokenCreateSerializer(serializers.ModelSerializer):
    company = serializers.SlugRelatedField(slug_field="uuid", queryset=Company.objects.none(), required=False)

    class Meta:
        model = ShareToken
        fields = [
            "company",
            "name",
            "symbol",
            "token_type",
            "total_supply",
            "decimals",
            "is_transferable",
            "is_divisible",
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        fields["company"].queryset = Company.objects.manageable_by_user(getattr(request, "user", None))
        return fields

    def validate_symbol(self, value):
        if not value.isalpha():
            raise serializers.ValidationError("Symbol must contain only letters.")
        if len(value) < 3 or len(value) > 5:
            raise serializers.ValidationError("Symbol must be 3-5 characters.")
        return value.upper()

    def validate_total_supply(self, value):
        try:
            supply = int(value)
            if supply <= 0:
                raise serializers.ValidationError("Total supply must be greater than zero.")
        except (ValueError, TypeError):
            raise serializers.ValidationError("Total supply must be a valid number.")
        return str(supply)

    def to_internal_value(self, data):
        attrs = super().to_internal_value(data)
        if attrs.get("company") is None:
            companies = list(self.fields["company"].queryset[:2])
            if len(companies) != 1:
                raise serializers.ValidationError({"company": "Select the company that issues this token."})
            attrs["company"] = companies[0]
        return attrs
