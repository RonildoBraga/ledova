from rest_framework import serializers

from users.models import Waitlist


class WaitlistCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Waitlist
        fields = ["email"]
