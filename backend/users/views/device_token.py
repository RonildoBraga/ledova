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


class DeviceTokenViewSet(AuthenticatedModelViewSet):
    serializer_class = DeviceTokenSerializer
    http_method_names = ["get", "post"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return DeviceToken.objects.visible_to_user(self.request.user).filter(is_active=True)

    @action(detail=False, methods=["post"], url_path="register")
    def register_token(self, request):
        serializer = RegisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        push_token = serializer.validated_data["push_token"]
        device_type = serializer.validated_data["device_type"]

        # A push token identifies an app install; whoever signed in on it last is its owner.
        device_token, created = DeviceToken.objects.update_or_create(
            push_token=push_token,
            defaults={"user": request.user, "device_type": device_type, "is_active": True},
        )

        if created:
            response_status = status.HTTP_201_CREATED
        else:
            response_status = status.HTTP_200_OK

        return Response(DeviceTokenSerializer(device_token).data, status=response_status)

    @action(detail=False, methods=["post"], url_path="unregister")
    def unregister_token(self, request):
        serializer = UnregisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        push_token = serializer.validated_data["push_token"]

        deleted_count, _ = DeviceToken.objects.visible_to_user(request.user).filter(push_token=push_token).delete()
        if deleted_count:
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {"detail": "Token not found or does not belong to this user."},
            status=status.HTTP_404_NOT_FOUND,
        )
