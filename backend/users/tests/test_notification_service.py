from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from users.models import DeviceToken, Notification, NotificationPreferences, UserProfile
from users.services.notifications import NotificationService

User = get_user_model()


class NotificationServiceDeviceTokenTest(TestCase):
    def test_token_deleted_during_send_is_not_resurrected(self):
        user = User.objects.create_user(email="push@example.test", password="pw-12345678")
        UserProfile.objects.create(user=user)
        token = DeviceToken.objects.create(
            user=user,
            push_token="ExponentPushToken[gone]",
            device_type=DeviceToken.DeviceType.IOS,
        )

        def send_batch(messages):
            DeviceToken.objects.filter(pk=token.pk).delete()
            return [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]

        with patch("users.services.notifications.ExpoPushClient"):
            service = NotificationService()
        service.expo_client = Mock(send_batch=send_batch)

        result = service.notify_user(user, "title", "body")

        self.assertEqual(result["status"], "sent")
        self.assertFalse(DeviceToken.objects.filter(pk=token.pk).exists())

    def test_unregistered_device_is_deactivated_in_place(self):
        user = User.objects.create_user(email="push2@example.test", password="pw-12345678")
        UserProfile.objects.create(user=user)
        token = DeviceToken.objects.create(
            user=user,
            push_token="ExponentPushToken[stale]",
            device_type=DeviceToken.DeviceType.IOS,
        )
        with patch("users.services.notifications.ExpoPushClient"):
            service = NotificationService()
        service.expo_client = Mock(
            send_batch=Mock(return_value=[{"status": "error", "details": {"error": "DeviceNotRegistered"}}])
        )

        service.notify_user(user, "title", "body")

        token.refresh_from_db()
        self.assertFalse(token.is_active)


class NotificationServicePreferencesTest(TestCase):
    def setUp(self):
        with patch("users.services.notifications.ExpoPushClient"):
            self.service = NotificationService()

    def test_user_without_profile_or_preferences_gets_exactly_one_row(self):
        user = User.objects.create_user(email="noprofile@example.test", password="pw-12345678")

        result = self.service.notify_user(user, "title", "body", notification_type="transaction")

        self.assertEqual(result["status"], "no_devices")
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_disabled_type_keeps_the_inbox_row_and_skips_the_push(self):
        user = User.objects.create_user(email="muted@example.test", password="pw-12345678")
        NotificationPreferences.objects.create(
            user_profile=UserProfile.objects.create(user=user), transaction_alerts=False
        )
        DeviceToken.objects.create(user=user, push_token="ExponentPushToken[muted]", device_type="ios")

        result = self.service.notify_user(user, "title", "body", notification_type="transaction")

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(Notification.objects.filter(user=user, notification_type="transaction").count(), 1)
        self.service.expo_client.send_batch.assert_not_called()
