from rest_framework import serializers

from feature_flags.models.feature_flag import FeatureFlag


class FeatureFlagSerializer(serializers.ModelSerializer):

    class Meta:
        model = FeatureFlag
        exclude = (
            "created_at",
            "updated_at",
        )
