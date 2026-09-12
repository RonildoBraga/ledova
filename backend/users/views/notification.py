from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views.base import AuthenticatedReadOnlyViewSet
from users.filters import NotificationFilter
from users.models.notification import Notification
from users.serializers.notification import (
    MarkAllReadResponseSerializer,
    NotificationSerializer,
    UnreadCountResponseSerializer,
)


class NotificationViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter
    http_method_names = ["get", "patch", "post", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return Notification.objects.for_the_current_principal().not_archived().with_optimized_data()

    def partial_update(self, request, **kwargs):
        notification = self.get_object()
        serializer = self.get_serializer(notification, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("is_read") and not notification.is_read:
            notification.mark_as_read()

        if serializer.validated_data.get("is_archived") and not notification.is_archived:
            notification.is_archived = True
            notification.save(update_fields=["is_archived", "updated_at"])

        return Response(self.get_serializer(notification).data)

    @extend_schema(responses=UnreadCountResponseSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = self.get_queryset().unread().count()
        return Response({"unreadCount": count})

    @extend_schema(responses=MarkAllReadResponseSerializer)
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().mark_all_read()
        return Response({"marked": updated}, status=status.HTTP_200_OK)
