import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedReadOnlyViewSet
from users.filters import NotificationFilter
from users.models.notification import Notification
from users.serializers.notification import NotificationSerializer

logger = logging.getLogger("ledova_backend")


class NotificationViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter
    http_method_names = ["get", "patch", "post", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return Notification.objects.for_user(self.request.user).not_archived().with_optimized_data()

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

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = Notification.objects.unread_count(request.user)
        return Response({"unreadCount": count})

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = Notification.objects.for_user(request.user).not_archived().mark_all_read()
        logger.info(f"{LoggingContext.NOTIFICATIONS} Marked {updated} notifications as read for {request.user.email}")
        return Response({"marked": updated}, status=status.HTTP_200_OK)
