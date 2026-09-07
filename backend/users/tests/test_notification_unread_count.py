from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import Notification

User = get_user_model()

UNREAD_COUNT = "/api/notifications/unread-count/"


class NotificationUnreadCountTest(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-count@example.test", password="pw-12345678")
        self.bob = User.objects.create_user(email="bob-count@example.test", password="pw-12345678")
        self.client.force_authenticate(self.alice)

    def _notify(self, user, **kwargs):
        return Notification.objects.create(user=user, title="Title", body="Body", **kwargs)

    def test_an_archived_notification_is_not_counted_even_when_unread(self):
        self._notify(self.alice, is_read=False, is_archived=True)
        self._notify(self.alice, is_read=False)

        self.assertEqual(self.client.get(UNREAD_COUNT).json(), {"unreadCount": 1})

    def test_a_read_notification_is_not_counted(self):
        self._notify(self.alice, is_read=True)

        self.assertEqual(self.client.get(UNREAD_COUNT).json(), {"unreadCount": 0})

    def test_another_users_unread_notification_is_not_counted(self):
        self._notify(self.bob, is_read=False)

        self.assertEqual(self.client.get(UNREAD_COUNT).json(), {"unreadCount": 0})

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(UNREAD_COUNT).status_code, 401)
