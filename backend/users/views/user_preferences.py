from rest_framework import status
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models.user_preferences import UserPreferences
from users.serializers.user_preferences import UserPreferencesSerializer
from users.services import upsert_user_preferences


class UserPreferencesViewSet(AuthenticatedModelViewSet):
    serializer_class = UserPreferencesSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return UserPreferences.objects.owned_through_the_live_profile(self.request.user)

    def list(self, request):
        preferences = self.get_queryset().first()
        if preferences is None:
            return Response(
                {"detail": "User preferences not found. Create them first."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(self.get_serializer(preferences).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data, partial=self.get_queryset().exists())
        serializer.is_valid(raise_exception=True)

        preferences = upsert_user_preferences(request.user, serializer.validated_data)

        return Response(self.get_serializer(preferences).data, status=status.HTTP_200_OK)
