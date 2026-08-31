"""
Serializers for waitlist functionality.
"""

from rest_framework import serializers

from users.models import Waitlist


class WaitlistSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and retrieving waitlist entries.
    """

    class Meta:
        model = Waitlist
        fields = ["email", "subscribed_at", "is_active"]
        read_only_fields = ["subscribed_at", "is_active"]

    def validate_email(self, value):
        """
        Validate that the email is not already in the waitlist.
        """
        if Waitlist.objects.filter(email=value, is_active=True).exists():
            raise serializers.ValidationError("This email is already on the waitlist.")
        return value


class WaitlistCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating waitlist entries with minimal fields.
    """

    class Meta:
        model = Waitlist
        fields = ["email"]

    def create(self, validated_data):
        """
        Create a new waitlist entry.
        """
        return Waitlist.objects.create(**validated_data)
