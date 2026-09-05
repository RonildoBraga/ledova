from rest_framework import serializers

from assets.models import Asset
from assets.serializers.asset import AssetSerializer
from users.models.favourite_asset import FavouriteAsset
from users.models.user_account import UserAccount


class FavouriteAssetSerializer(serializers.ModelSerializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.active().verified())
    user_account = serializers.PrimaryKeyRelatedField(queryset=UserAccount.objects.none())

    class Meta:
        model = FavouriteAsset
        fields = (
            "uuid",
            "user_account",
            "asset",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "created_at",
            "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        if request and request.user:
            user_profile = getattr(request.user, "userprofile", None)
            if user_profile:
                fields["user_account"].queryset = user_profile.user_accounts.all()

        return fields

    def validate_user_account(self, value):
        request = self.context.get("request")
        if request and request.user:
            user_profile = getattr(request.user, "userprofile", None)
            if user_profile and value not in user_profile.user_accounts.all():
                raise serializers.ValidationError("The user account must be one of your accounts.")
        return value

    def validate(self, attrs):
        user_account = attrs.get("user_account")
        asset = attrs.get("asset")

        if user_account and asset:
            if FavouriteAsset.objects.filter(user_account=user_account, asset=asset).exists():
                raise serializers.ValidationError({"asset": f"{asset.symbol} is already in your favourites."})

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["asset"] = AssetSerializer(instance.asset).data
        return data
