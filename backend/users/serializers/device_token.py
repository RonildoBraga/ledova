"""
Serializers for device tokens.
"""

from rest_framework import serializers

from users.models import DeviceToken


class DeviceTokenSerializer(serializers.ModelSerializer):
    """
    Serializer for the DeviceToken model.

    Used for reading device token data.
    """

    class Meta:
        model = DeviceToken
        fields = (
            "uuid",
            "push_token",
            "device_type",
            "is_active",
            "last_used_at",
            "created_at",
        )
        read_only_fields = ("uuid", "last_used_at", "created_at")


class RegisterDeviceTokenSerializer(serializers.Serializer):
    """
    Serializer for registering a new device token.

    Validates the push token format and device type.
    """

    push_token = serializers.CharField(
        max_length=255,
        help_text="Expo push token (e.g., ExponentPushToken[xxx])",
    )
    device_type = serializers.ChoiceField(
        choices=DeviceToken.DeviceType.choices,
        help_text="Device platform (ios or android)",
    )

    def validate_push_token(self, value):
        """Validate the push token format."""
        if not DeviceToken.validate_expo_token(value):
            raise serializers.ValidationError(
                "Invalid Expo push token format. Token must start with 'ExponentPushToken[' and end with ']'."
            )
        return value


class UnregisterDeviceTokenSerializer(serializers.Serializer):
    """
    Serializer for unregistering a device token.
    """

    push_token = serializers.CharField(
        max_length=255,
        help_text="Expo push token to unregister",
    )
