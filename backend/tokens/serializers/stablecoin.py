from rest_framework import serializers

from tokens.models import Stablecoin


class StablecoinListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stablecoin
        fields = (
            "uuid",
            "name",
            "symbol",
            "contract_address",
            "decimals",
        )


class StablecoinTransparencySerializer(serializers.ModelSerializer):
    total_supply = serializers.SerializerMethodField()
    chain_deployments = serializers.SerializerMethodField()

    class Meta:
        model = Stablecoin
        fields = (
            "uuid",
            "name",
            "symbol",
            "decimals",
            "total_supply",
            "reserve_amount",
            "reserve_updated_at",
            "chain_deployments",
        )

    def get_total_supply(self, obj) -> str | None:
        return self.context.get("total_supply")

    def get_chain_deployments(self, obj) -> list:
        return self.context.get("chain_deployments", [])
