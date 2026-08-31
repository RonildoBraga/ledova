from rest_framework import serializers

from tokens.models import NAVUpdate, YieldToken


class YieldTokenSerializer(serializers.ModelSerializer):

    class Meta:
        model = YieldToken
        fields = (
            "uuid",
            "symbol",
            "name",
            "contract_address",
            "decimals",
            "nav_per_token",
            "total_reserve_value",
            "last_nav_update",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class NAVUpdateSerializer(serializers.ModelSerializer):

    yield_token_symbol = serializers.CharField(source="yield_token.symbol", read_only=True)

    class Meta:
        model = NAVUpdate
        fields = (
            "uuid",
            "yield_token_symbol",
            "old_nav_per_token",
            "new_nav_per_token",
            "total_reserve_value",
            "custodian_report_ref",
            "notes",
            "created_at",
        )
        read_only_fields = fields
