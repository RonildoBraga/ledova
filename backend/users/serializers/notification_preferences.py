"""
Serializers for notification preferences.
"""

from rest_framework import serializers

from users.models import NotificationPreferences


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    """
    Serializer for the NotificationPreferences model.

    Handles reading and updating notification preferences.
    """

    user_profile = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = NotificationPreferences
        fields = (
            "uuid",
            "user_profile",
            "transaction_alerts",
            "price_alerts",
            "marketing",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "user_profile", "created_at", "updated_at")
