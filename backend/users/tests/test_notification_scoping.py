"""Behaviour tests for notifications, notification preferences, device tokens and identity verification."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import DeviceToken, Notification, NotificationPreferences, UserProfile
from users.services import IdentityVerificationService

User = get_user_model()

NOTIFICATIONS = "/api/notifications/"
PREFERENCES = "/api/notification-preferences/"
IDENTITY_TOKEN = "/api/users/identity-verification/token/"
IDENTITY_STATUS = "/api/users/identity-verification/status/"


class NotificationScopingTest(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-notif@example.test", password="pw-12345678")
        self.bob = User.objects.create_user(email="bob-notif@example.test", password="pw-12345678")
        self.profiles = {user: UserProfile.objects.create(user=user) for user in (self.alice, self.bob)}
        self.notifications = {
            user: Notification.objects.create(user=user, title=f"For {user.email}", body="Body")
            for user in (self.alice, self.bob)
        }
        self.bob_preferences = NotificationPreferences.objects.create(user_profile=self.profiles[self.bob])
        self.alice_token = DeviceToken.objects.create(
            user=self.alice, push_token="ExponentPushToken[alice]", device_type="ios"
        )
        self.bob_token = DeviceToken.objects.create(
            user=self.bob, push_token="ExponentPushToken[bob]", device_type="ios"
        )

    @staticmethod
    def _rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_notification_routes_are_owner_scoped(self):
        self.client.force_authenticate(self.alice)
        own, foreign = self.notifications[self.alice], self.notifications[self.bob]

        list_response = self.client.get(NOTIFICATIONS)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual({row["uuid"] for row in self._rows(list_response)}, {str(own.uuid)})

        self.assertEqual(self.client.get(f"{NOTIFICATIONS}{foreign.uuid}/").status_code, 404)
        self.assertEqual(
            self.client.patch(f"{NOTIFICATIONS}{foreign.uuid}/", {"isRead": True}, format="json").status_code, 404
        )
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)

        self.assertEqual(self.client.get(f"{NOTIFICATIONS}unread-count/").json(), {"unreadCount": 1})
        marked = self.client.post(f"{NOTIFICATIONS}mark-all-read/")
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json(), {"marked": 1})
        self.assertEqual(self.client.get(f"{NOTIFICATIONS}unread-count/").json(), {"unreadCount": 0})
        self.assertEqual(Notification.objects.unread_count(self.bob), 1)

        own.refresh_from_db()
        self.assertTrue(own.is_read)
        archived = self.client.patch(f"{NOTIFICATIONS}{own.uuid}/", {"isArchived": True}, format="json")
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(self._rows(self.client.get(NOTIFICATIONS)), [])

    def test_notification_preferences_are_owner_scoped(self):
        self.client.force_authenticate(self.alice)
        alice_profile = self.profiles[self.alice]

        self.assertFalse(NotificationPreferences.objects.filter(user_profile=alice_profile).exists())
        list_response = self.client.get(PREFERENCES)
        self.assertEqual(list_response.status_code, 200)
        own = NotificationPreferences.objects.get(user_profile=alice_profile)
        self.assertEqual(list_response.json()["uuid"], str(own.uuid))
        self.assertEqual(NotificationPreferences.objects.count(), 2)

        foreign_patch = self.client.patch(f"{PREFERENCES}{self.bob_preferences.uuid}/", {"marketing": True})
        self.assertEqual(foreign_patch.status_code, 404)
        self.assertEqual(self.client.get(f"{PREFERENCES}{self.bob_preferences.uuid}/").status_code, 404)
        self.bob_preferences.refresh_from_db()
        self.assertFalse(self.bob_preferences.marketing)

        own_patch = self.client.patch(f"{PREFERENCES}{own.uuid}/", {"marketing": True}, format="json")
        self.assertEqual(own_patch.status_code, 200)
        own_post = self.client.post(PREFERENCES, {"priceAlerts": True}, format="json")
        self.assertEqual(own_post.status_code, 200)
        own.refresh_from_db()
        self.assertTrue(own.marketing)
        self.assertTrue(own.price_alerts)
        self.assertEqual(NotificationPreferences.objects.count(), 2)

    def test_device_token_manager_is_owner_scoped(self):
        self.assertEqual(set(DeviceToken.objects.visible_to_user(self.alice)), {self.alice_token})
        self.assertEqual(set(NotificationPreferences.objects.visible_to_user(self.bob)), {self.bob_preferences})
        self.assertFalse(NotificationPreferences.objects.visible_to_user(self.alice).exists())

    def test_identity_verification_uses_only_the_requesters_profile(self):
        self.client.force_authenticate(self.alice)
        session = SimpleNamespace(provider="sumsub", applicant_id="app-1", access_token="tok", form_url="https://f")

        with patch.object(IdentityVerificationService, "get_verification_session", return_value=session) as start:
            token_response = self.client.post(IDENTITY_TOKEN)
        self.assertEqual(token_response.status_code, 200)
        self.assertEqual(
            token_response.json(),
            {"provider": "sumsub", "applicantId": "app-1", "accessToken": "tok", "formUrl": "https://f"},
        )
        start.assert_called_once_with(self.profiles[self.alice])

        with patch.object(IdentityVerificationService, "get_verification_status", return_value={"status": "x"}) as st:
            status_response = self.client.get(IDENTITY_STATUS)
        self.assertEqual(status_response.status_code, 200)
        st.assert_called_once_with(self.profiles[self.alice])

    def test_user_without_profile_gets_404_not_500(self):
        orphan = User.objects.create_user(email="orphan@example.test", password="pw-12345678")
        self.client.force_authenticate(orphan)

        with patch.object(IdentityVerificationService, "get_verification_session") as start, patch.object(
            IdentityVerificationService, "get_verification_status"
        ) as st:
            for method, url in (
                ("get", PREFERENCES),
                ("post", PREFERENCES),
                ("get", "/api/user-preferences/"),
                ("post", "/api/user-preferences/"),
                ("post", IDENTITY_TOKEN),
                ("get", IDENTITY_STATUS),
            ):
                with self.subTest(method=method, url=url):
                    self.assertEqual(getattr(self.client, method)(url, {}, format="json").status_code, 404)
        start.assert_not_called()
        st.assert_not_called()
        self.assertEqual(self._rows(self.client.get(NOTIFICATIONS)), [])
        self.assertEqual(NotificationPreferences.objects.count(), 1)

    def test_anonymous_is_rejected(self):
        for method, url in (
            ("get", NOTIFICATIONS),
            ("get", f"{NOTIFICATIONS}unread-count/"),
            ("post", f"{NOTIFICATIONS}mark-all-read/"),
            ("get", PREFERENCES),
            ("post", PREFERENCES),
            ("get", "/api/device-tokens/"),
            ("post", IDENTITY_TOKEN),
            ("get", IDENTITY_STATUS),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, {}, format="json").status_code, 401)
