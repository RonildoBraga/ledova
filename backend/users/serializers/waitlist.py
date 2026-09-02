"""
Serializers for waitlist functionality.
"""

from rest_framework import serializers

from users.models import Waitlist


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
