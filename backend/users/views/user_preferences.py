import logging

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models.user_preferences import UserPreferences
from users.serializers.user_preferences import UserPreferencesSerializer

logger = logging.getLogger("ledova_backend")


class UserPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = UserPreferencesSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return UserPreferences.objects.visible_to_user(self.request.user).filter(
            user_profile=self.request.user.userprofile
        )

    def list(self, request):
        try:
            preferences = UserPreferences.objects.get(user_profile=request.user.userprofile)
            serializer = self.get_serializer(preferences)
            return Response(serializer.data)
        except UserPreferences.DoesNotExist:
            return Response(
                {"detail": "User preferences not found. Create them first."}, status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request):
        with transaction.atomic():
            try:
                preferences = UserPreferences.objects.select_for_update().get(user_profile=request.user.userprofile)
                serializer = self.get_serializer(preferences, data=request.data, partial=True)
            except UserPreferences.DoesNotExist:
                serializer = self.get_serializer(data=request.data)

            serializer.is_valid(raise_exception=True)
            serializer.save(user_profile=request.user.userprofile)

            return Response(serializer.data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)

    def perform_update(self, serializer):
        serializer.save(user_profile=self.request.user.userprofile)
