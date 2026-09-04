from rest_framework import serializers

from users.models import DeviceToken


class DeviceTokenSerializer(serializers.ModelSerializer):
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
    push_token = serializers.CharField(
        max_length=255,
        help_text="Expo push token (e.g., ExponentPushToken[xxx])",
    )
    device_type = serializers.ChoiceField(
        choices=DeviceToken.DeviceType.choices,
        help_text="Device platform (ios or android)",
    )

    def validate_push_token(self, value):
        if not (value.startswith("ExponentPushToken[") and value.endswith("]")):
            raise serializers.ValidationError(
                "Invalid Expo push token format. Token must start with 'ExponentPushToken[' and end with ']'."
            )
        return value


class UnregisterDeviceTokenSerializer(serializers.Serializer):
    push_token = serializers.CharField(
        max_length=255,
        help_text="Expo push token to unregister",
    )
