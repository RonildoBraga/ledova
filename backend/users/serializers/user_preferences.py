from rest_framework import serializers

from portfolios.models.portfolio import Portfolio
from users.models import UserAccount, UserPreferences


class SelectedAccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserAccount
        fields = ("uuid", "account_number", "account_type", "activation_date", "role")
        read_only_fields = fields


class SelectedPortfolioSerializer(serializers.ModelSerializer):

    user_account = serializers.UUIDField(source="user_account.uuid", read_only=True)

    class Meta:
        model = Portfolio
        fields = ("uuid", "user_account", "name", "is_active")
        read_only_fields = fields


class UserPreferencesSerializer(serializers.ModelSerializer):

    user_profile = serializers.PrimaryKeyRelatedField(read_only=True)
    selected_account = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True, queryset=UserAccount.objects.none()
    )
    selected_portfolio = serializers.PrimaryKeyRelatedField(
        required=False, allow_null=True, queryset=Portfolio.objects.none()
    )

    class Meta:
        model = UserPreferences
        exclude = ("created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        if request and request.user:
            user_profile = getattr(request.user, "userprofile", None)
            if user_profile:
                fields["selected_account"].queryset = user_profile.user_accounts.all()

                user_portfolios = Portfolio.objects.filter(user_account__in=user_profile.user_accounts.all())
                fields["selected_portfolio"].queryset = user_portfolios

        return fields

    def validate(self, data):
        """get_fields already limits both querysets to the user's own rows, so only the cross-field rule is left."""
        selected_account = data.get("selected_account")
        selected_portfolio = data.get("selected_portfolio")

        if selected_portfolio and not selected_account:
            data["selected_account"] = selected_account = selected_portfolio.user_account

        if selected_portfolio and selected_account and selected_portfolio.user_account != selected_account:
            raise serializers.ValidationError(
                {"selected_portfolio": "The selected portfolio must belong to the selected account."}
            )

        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        live_account_ids = set(instance.user_profile.user_accounts.values_list("pk", flat=True))

        if instance.selected_account_id in live_account_ids:
            representation["selected_account"] = SelectedAccountSerializer(instance.selected_account).data
        else:
            representation["selected_account"] = None

        if instance.selected_portfolio and instance.selected_portfolio.user_account_id in live_account_ids:
            representation["selected_portfolio"] = SelectedPortfolioSerializer(instance.selected_portfolio).data
        else:
            representation["selected_portfolio"] = None

        return representation
