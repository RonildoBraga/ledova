from rest_framework import serializers

from users.models.financial_profile import FinancialProfile


class FinancialProfileSerializer(serializers.ModelSerializer):
    user_profile = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = FinancialProfile
        exclude = ("created_at", "updated_at")
