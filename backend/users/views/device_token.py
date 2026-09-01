import logging

from django.db import IntegrityError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from users.models import DeviceToken
from users.serializers import (
    DeviceTokenSerializer,
    RegisterDeviceTokenSerializer,
    UnregisterDeviceTokenSerializer,
)

logger = logging.getLogger("ledova_backend")


class DeviceTokenViewSet(AuthenticatedModelViewSet):
    serializer_class = DeviceTokenSerializer
    http_method_names = ["get", "post"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user, is_active=True)

    @action(detail=False, methods=["post"], url_path="register")
    def register_token(self, request):
        serializer = RegisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        push_token = serializer.validated_data["push_token"]
        device_type = serializer.validated_data["device_type"]

        try:
            device_token, created = DeviceToken.objects.update_or_create(
                user=request.user,
                push_token=push_token,
                defaults={"device_type": device_type, "is_active": True},
            )
        except IntegrityError:
            return Response(
                {"detail": "Device token registration conflict."},
                status=status.HTTP_409_CONFLICT,
            )

        if created:
            logger.info(f"{LoggingContext.DEVICE_TOKEN} Registered new token for user {request.user.email}")
            response_status = status.HTTP_201_CREATED
        else:
            logger.info(f"{LoggingContext.DEVICE_TOKEN} Reactivated token for user {request.user.email}")
            response_status = status.HTTP_200_OK

        return Response(DeviceTokenSerializer(device_token).data, status=response_status)

    @action(detail=False, methods=["post"], url_path="unregister")
    def unregister_token(self, request):
        serializer = UnregisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        push_token = serializer.validated_data["push_token"]

        deleted_count, _ = DeviceToken.objects.filter(
            user=request.user,
            push_token=push_token,
        ).delete()
        if deleted_count:
            logger.info(f"{LoggingContext.DEVICE_TOKEN} Unregistered token for user {request.user.email}")
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {"detail": "Token not found or does not belong to this user."},
            status=status.HTTP_404_NOT_FOUND,
        )
