from feature_flags.models.feature_flag import FeatureFlag
from feature_flags.serializers.feature_flag import FeatureFlagSerializer
from shared.views.base import AuthenticatedReadOnlyViewSet


class FeatureFlagViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = FeatureFlagSerializer
    ordering = ["name"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        return FeatureFlag.objects.filter(enabled=True)
