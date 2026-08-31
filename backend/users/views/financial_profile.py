import logging

from shared.views.base import AuthenticatedModelViewSet
from users.models.financial_profile import FinancialProfile
from users.serializers.financial_profile import FinancialProfileSerializer

logger = logging.getLogger("ledova_backend")


class FinancialProfileViewSet(AuthenticatedModelViewSet):
    serializer_class = FinancialProfileSerializer

    ordering = ["created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return FinancialProfile.objects.visible_to_user(self.request.user)

    def perform_create(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)

    def perform_update(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)
