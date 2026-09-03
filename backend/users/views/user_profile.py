import logging

from django.db import transaction
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.models.user_profile import UserProfile
from users.serializers import UserProfileSerializer
from users.services import lifecycle

logger = logging.getLogger("ledova_backend")


class UserProfileViewSet(AuthenticatedModelViewSet):
    serializer_class = UserProfileSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "full_name"]

    def get_queryset(self):
        queryset = UserProfile.objects.visible_to_user(self.request.user).select_related("citizenship_country")
        if getattr(self, "action", None) in {"update", "partial_update"}:
            return queryset.select_for_update(of=("self",))
        return queryset

    def perform_create(self, serializer):
        logger.info(f"{LoggingContext.USER_PROFILE} Creating user profile")
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        logger.info(f"{LoggingContext.USER_PROFILE} Updating user profile")
        serializer.save()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="delete-account")
    def delete_account(self, request):
        lifecycle.delete_account(request.user)
        return Response({"message": "Your account has been successfully deleted."})

    @action(detail=False, methods=["get"], url_path="export-data")
    def export_data(self, request):
        return Response(lifecycle.export_account_data(request.user))
