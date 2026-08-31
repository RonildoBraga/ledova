import logging

from django.db import transaction
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

        with transaction.atomic():
            existing_token = DeviceToken.objects.filter(push_token=push_token).first()

            if existing_token:
                if existing_token.user == request.user:
                    existing_token.is_active = True
                    existing_token.device_type = device_type
                    existing_token.save()
                    logger.info(f"{LoggingContext.DEVICE_TOKEN} Reactivated token for user {request.user.email}")
                else:
                    existing_token.user = request.user
                    existing_token.is_active = True
                    existing_token.device_type = device_type
                    existing_token.save()
                    logger.info(
                        f"{LoggingContext.DEVICE_TOKEN} Transferred token from {existing_token.user.email} "
                        f"to {request.user.email}"
                    )

                return Response(
                    DeviceTokenSerializer(existing_token).data,
                    status=status.HTTP_200_OK,
                )
            else:
                device_token = DeviceToken.objects.create(
                    user=request.user,
                    push_token=push_token,
                    device_type=device_type,
                    is_active=True,
                )
                logger.info(f"{LoggingContext.DEVICE_TOKEN} Registered new token for user {request.user.email}")

                return Response(
                    DeviceTokenSerializer(device_token).data,
                    status=status.HTTP_201_CREATED,
                )

    @action(detail=False, methods=["post"], url_path="unregister")
    def unregister_token(self, request):
        serializer = UnregisterDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        push_token = serializer.validated_data["push_token"]

        try:
            device_token = DeviceToken.objects.get(
                user=request.user,
                push_token=push_token,
            )
            device_token.is_active = False
            device_token.save()
            logger.info(f"{LoggingContext.DEVICE_TOKEN} Unregistered token for user {request.user.email}")

            return Response(status=status.HTTP_204_NO_CONTENT)

        except DeviceToken.DoesNotExist:
            return Response(
                {"detail": "Token not found or does not belong to this user."},
                status=status.HTTP_404_NOT_FOUND,
            )
