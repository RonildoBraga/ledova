import logging

from django.db import transaction

from compliance.services.risk_assessment import RiskAssessmentService
from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.constants import USER_ACCOUNT_TYPE_INDIVIDUAL
from users.models import UserAccount
from users.serializers.user_account import UserAccountSerializer

logger = logging.getLogger("ledova_backend")


class UserAccountViewSet(AuthenticatedModelViewSet):
    serializer_class = UserAccountSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    ordering = ["-activation_date"]
    ordering_fields = ["activation_date", "created_at"]

    def get_queryset(self):
        queryset = UserAccount.objects.visible_to_user(self.request.user)
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return queryset.select_for_update()
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        profile = self.request.user.userprofile
        logger.info(f"{LoggingContext.ACCOUNT_CREATION} Creating customer account for user: {self.request.user.email}")
        account = serializer.save()
        account.user_profiles.add(profile)
        if account.account_type == USER_ACCOUNT_TYPE_INDIVIDUAL:
            account.director = profile
            account.save(update_fields=["director"])
        RiskAssessmentService.create_pending_assessment(user_account=account)

    def perform_update(self, serializer):
        return serializer.save()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
