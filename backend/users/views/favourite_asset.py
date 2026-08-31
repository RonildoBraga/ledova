import logging

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.filters import FavouriteAssetFilter
from users.models.favourite_asset import FavouriteAsset
from users.serializers.favourite_asset import FavouriteAssetSerializer

logger = logging.getLogger("ledova_backend")


class FavouriteAssetViewSet(AuthenticatedModelViewSet):
    serializer_class = FavouriteAssetSerializer
    filterset_class = FavouriteAssetFilter
    http_method_names = ["get", "post", "delete", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return FavouriteAsset.objects.visible_to_user(self.request.user).with_optimized_data()

    def perform_create(self, serializer):
        logger.info(f"{LoggingContext.ACCOUNTS} Adding favourite asset for user {self.request.user.email}")
        serializer.save()

    def perform_destroy(self, instance):
        logger.info(
            f"{LoggingContext.ACCOUNTS} Removing favourite asset {instance.asset.symbol} "
            f"for user {self.request.user.email}"
        )
        instance.delete()
