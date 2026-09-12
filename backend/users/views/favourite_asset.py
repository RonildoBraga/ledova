from shared.views.base import AuthenticatedModelViewSet
from users.filters import FavouriteAssetFilter
from users.models.favourite_asset import FavouriteAsset
from users.serializers.favourite_asset import FavouriteAssetSerializer


class FavouriteAssetViewSet(AuthenticatedModelViewSet):
    serializer_class = FavouriteAssetSerializer
    filterset_class = FavouriteAssetFilter
    http_method_names = ["get", "post", "delete", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    scoped_model = FavouriteAsset

    def narrow(self, queryset):
        return queryset.filter(asset__is_verified=True).with_optimized_data()

    def perform_create(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()
