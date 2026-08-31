import logging

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.models import NotificationPreferences
from users.serializers import NotificationPreferencesSerializer

logger = logging.getLogger("ledova_backend")


class NotificationPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = NotificationPreferencesSerializer
    http_method_names = ["get", "post", "patch"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return NotificationPreferences.objects.filter(user_profile=self.request.user.userprofile)

    def list(self, request):
        preferences, created = NotificationPreferences.objects.get_or_create(
            user_profile=request.user.userprofile,
            defaults={
                "transaction_alerts": True,
                "price_alerts": False,
                "marketing": False,
            },
        )

        if created:
            logger.info(f"{LoggingContext.NOTIFICATION_PREFS} Created default preferences for {request.user.email}")

        serializer = self.get_serializer(preferences)
        return Response(serializer.data)

    def create(self, request):
        with transaction.atomic():
            try:
                preferences = NotificationPreferences.objects.select_for_update().get(
                    user_profile=request.user.userprofile
                )
                serializer = self.get_serializer(preferences, data=request.data, partial=True)
            except NotificationPreferences.DoesNotExist:
                serializer = self.get_serializer(data=request.data)

            serializer.is_valid(raise_exception=True)
            serializer.save(user_profile=request.user.userprofile)

            logger.info(f"{LoggingContext.NOTIFICATION_PREFS} Updated preferences for {request.user.email}")

            return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        return self.create(request)

    def perform_create(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)

    def perform_update(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)
