import logging

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.models import UserAccount
from users.serializers.user_account import UserAccountSerializer

logger = logging.getLogger("ledova_backend")


class UserAccountViewSet(AuthenticatedModelViewSet):
    serializer_class = UserAccountSerializer

    ordering = ["-activation_date"]
    ordering_fields = ["activation_date", "created_at"]

    def get_queryset(self):
        return UserAccount.objects.visible_to_user(self.request.user)

    def perform_create(self, serializer):
        logger.info(f"{LoggingContext.ACCOUNT_CREATION} Creating customer account for user: {self.request.user.email}")
        return serializer.save(user_profiles=[self.request.user.userprofile])

    def perform_update(self, serializer):
        return serializer.save(user_profiles=[self.request.user.userprofile])
