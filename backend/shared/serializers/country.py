from rest_framework import serializers

from shared.models.country import Country


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ("uuid", "name", "code", "dial_code", "is_available")
        read_only_fields = ("uuid",)
