from django.db import transaction
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models import NotificationPreferences, UserProfile
from users.serializers import NotificationPreferencesSerializer
from users.services import ensure_notification_preferences


class NotificationPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = NotificationPreferencesSerializer
    http_method_names = ["get", "post", "patch"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = NotificationPreferences.objects.visible_to_user(self.request.user)
        if self.action == "create":
            return queryset.select_for_update()
        return queryset

    def list(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        preferences = ensure_notification_preferences(user_profile)

        serializer = self.get_serializer(preferences)
        return Response(serializer.data)

    @transaction.atomic
    def create(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        existing = self.get_queryset().first()

        serializer = self.get_serializer(existing, data=request.data, partial=existing is not None)
        serializer.is_valid(raise_exception=True)
        serializer.save(user_profile=user_profile)

        return Response(serializer.data, status=status.HTTP_200_OK)
