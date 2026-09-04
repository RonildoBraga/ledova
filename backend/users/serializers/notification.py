from rest_framework import serializers

from users.models.notification import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "uuid",
            "title",
            "body",
            "notification_type",
            "data",
            "is_read",
            "read_at",
            "is_archived",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "title",
            "body",
            "notification_type",
            "data",
            "read_at",
            "created_at",
            "updated_at",
        )
