from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models import NotificationPreferences, UserProfile
from users.serializers import NotificationPreferencesSerializer
from users.services import (
    ensure_notification_preferences,
    upsert_notification_preferences,
)


class NotificationPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = NotificationPreferencesSerializer
    http_method_names = ["get", "post", "patch"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    scoped_model = NotificationPreferences

    def list(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        preferences = ensure_notification_preferences(user_profile)

        serializer = self.get_serializer(preferences)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data, partial=self.get_queryset().exists())
        serializer.is_valid(raise_exception=True)

        preferences = upsert_notification_preferences(request.user, serializer.validated_data)

        return Response(self.get_serializer(preferences).data, status=status.HTTP_200_OK)
