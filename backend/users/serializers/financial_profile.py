"""
Serializers for financial profile.
"""

from rest_framework import serializers

from users.models.financial_profile import FinancialProfile


class FinancialProfileSerializer(serializers.ModelSerializer):
    """Serializer for the FinancialProfile model."""

    user_profile = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = FinancialProfile
        exclude = ("created_at", "updated_at")

    # No need for get_fields() - user_profile is read-only
