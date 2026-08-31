from rest_framework import serializers

from users.models import UserAccount
from users.services import UserAccountService


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
            "account_number",
            "activation_date",
        )

    def create(self, validated_data):
        account = UserAccountService.create_customer_account(
            account_data=validated_data, user_profiles=validated_data.pop("user_profiles", [])
        )

        return account
