import logging

from django.db import transaction

from shared.views.base import AuthenticatedModelViewSet
from users.models.financial_profile import FinancialProfile
from users.serializers.financial_profile import FinancialProfileSerializer

logger = logging.getLogger("ledova_backend")


class FinancialProfileViewSet(AuthenticatedModelViewSet):
    serializer_class = FinancialProfileSerializer

    ordering = ["created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = FinancialProfile.objects.visible_to_user(self.request.user)
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return queryset.select_for_update()
        return queryset

    def perform_create(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)

    def perform_update(self, serializer):
        serializer.save()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
