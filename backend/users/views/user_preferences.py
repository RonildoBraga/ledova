import logging

from django.db import transaction
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models.user_preferences import UserPreferences
from users.models.user_profile import UserProfile
from users.serializers.user_preferences import UserPreferencesSerializer

logger = logging.getLogger("ledova_backend")


class UserPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = UserPreferencesSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return UserPreferences.objects.visible_to_user(self.request.user)

    def list(self, request):
        preferences = self.get_queryset().first()
        if preferences is None:
            return Response(
                {"detail": "User preferences not found. Create them first."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(self.get_serializer(preferences).data)

    def create(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        with transaction.atomic():
            try:
                preferences = UserPreferences.objects.select_for_update().get(user_profile=user_profile)
                serializer = self.get_serializer(preferences, data=request.data, partial=True)
            except UserPreferences.DoesNotExist:
                serializer = self.get_serializer(data=request.data)

            serializer.is_valid(raise_exception=True)
            serializer.save(user_profile=user_profile)

            return Response(serializer.data, status=status.HTTP_200_OK)
