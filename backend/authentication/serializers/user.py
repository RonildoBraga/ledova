from django.contrib.auth import get_user_model
from rest_framework import serializers

from authentication.models.user_token import UserToken
from authentication.serializers.fields import V2EmailField
from shared.constants import DATETIME_FORMAT

User = get_user_model()


class UserTokenSerializer(serializers.ModelSerializer):
    expires_at = serializers.DateTimeField(format=DATETIME_FORMAT, required=False)
    last_used_at = serializers.DateTimeField(format=DATETIME_FORMAT, required=False, allow_null=True)
    revoked_at = serializers.DateTimeField(format=DATETIME_FORMAT, required=False, allow_null=True)
    created_at = serializers.DateTimeField(format=DATETIME_FORMAT, required=False, allow_null=True)
    updated_at = serializers.DateTimeField(format=DATETIME_FORMAT, required=False, allow_null=True)

    class Meta:
        model = UserToken
        exclude = ["uuid", "user"]


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    email = V2EmailField(required=True)

    def to_representation(self, instance):
        representation = {
            "uuid": str(instance.userprofile.uuid) if hasattr(instance, "userprofile") else None,
            "email": instance.email,
            "is_email_verified": instance.is_email_verified,
            "is_phone_verified": getattr(instance, "is_phone_verified", False),
        }

        if hasattr(instance, "tokens"):
            tokens_qs = instance.tokens.filter(is_active=True).order_by("-created_at")
            representation["tokens"] = UserTokenSerializer(tokens_qs, many=True).data

        return representation


class UserSignupSerializer(serializers.Serializer):
    email = V2EmailField(required=True)
    password = serializers.CharField(max_length=255, write_only=True, required=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(
        max_length=255, write_only=True, required=True, style={"input_type": "password"}
    )

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value

    def to_representation(self, instance):
        representation = {
            "uuid": str(instance.userprofile.uuid) if hasattr(instance, "userprofile") else None,
            "email": instance.email,
            "is_email_verified": instance.is_email_verified,
            "is_phone_verified": getattr(instance, "is_phone_verified", False),
        }
        return representation


class UserSigninSerializer(serializers.Serializer):
    email = V2EmailField(required=True)
    password = serializers.CharField(max_length=255, write_only=True, required=True, style={"input_type": "password"})
    tokens = UserTokenSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        representation = {
            "uuid": str(instance.userprofile.uuid),
            "email": instance.email,
            "is_email_verified": instance.is_email_verified,
            "is_phone_verified": getattr(instance, "is_phone_verified", False),
        }

        if hasattr(instance, "tokens"):
            tokens_qs = instance.tokens.filter(is_active=True).order_by("-created_at")
            representation["tokens"] = UserTokenSerializer(tokens_qs, many=True).data

        return representation


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        max_length=255, write_only=True, required=True, style={"input_type": "password"}
    )
    new_password = serializers.CharField(
        max_length=255, write_only=True, required=True, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        max_length=255, write_only=True, required=True, style={"input_type": "password"}
    )

    def validate_new_password(self, value):
        """Validate new password meets requirements"""
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "New passwords do not match."})

        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "New password must be different from current password."})

        return attrs
