from django.db import transaction
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models.user_preferences import UserPreferences
from users.models.user_profile import UserProfile
from users.serializers.user_preferences import UserPreferencesSerializer


class UserPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = UserPreferencesSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = UserPreferences.objects.visible_to_user(self.request.user)
        if self.action == "create":
            return queryset.select_for_update()
        return queryset

    def list(self, request):
        preferences = self.get_queryset().first()
        if preferences is None:
            return Response(
                {"detail": "User preferences not found. Create them first."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(self.get_serializer(preferences).data)

    @transaction.atomic
    def create(self, request):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        existing = self.get_queryset().first()

        serializer = self.get_serializer(existing, data=request.data, partial=existing is not None)
        serializer.is_valid(raise_exception=True)
        serializer.save(user_profile=user_profile)

        return Response(serializer.data, status=status.HTTP_200_OK)
