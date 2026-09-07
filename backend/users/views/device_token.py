from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views.base import AuthenticatedModelViewSet
from users.models import DeviceToken
from users.serializers import (
    DeviceTokenSerializer,
    RegisterDeviceTokenSerializer,
    UnregisterDeviceTokenSerializer,
)
from users.services import register_device_token, unregister_device_token


class DeviceTokenViewSet(AuthenticatedModelViewSet):
    serializer_class = DeviceTokenSerializer
    http_method_names = ["get", "post"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return DeviceToken.objects.visible_to_user(self.request.user).filter(is_active=True)

    @action(detail=False, methods=["post"], url_path="register")
    @extend_schema(responses=DeviceTokenSerializer)
    def register_token(self, request):
        serializer = RegisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_token, created = register_device_token(
            request.user,
            serializer.validated_data["push_token"],
            serializer.validated_data["device_type"],
        )

        return Response(
            DeviceTokenSerializer(device_token).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="unregister")
    def unregister_token(self, request):
        serializer = UnregisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if unregister_device_token(request.user, serializer.validated_data["push_token"]):
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {"detail": "Token not found or does not belong to this user."},
            status=status.HTTP_404_NOT_FOUND,
        )
