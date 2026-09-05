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
