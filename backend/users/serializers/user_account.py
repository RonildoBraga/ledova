from rest_framework import serializers

from users.models import UserAccount


class UserAccountSerializer(serializers.ModelSerializer):
    uuid = serializers.CharField(read_only=True)

    class Meta:
        model = UserAccount
        fields = (
            "uuid",
            "director",
            "account_number",
            "account_type",
            "activation_date",
            "role",
        )
        read_only_fields = (
            "uuid",
            "director",
            "account_number",
            "activation_date",
        )
