import threading
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APITestCase

from users.models import NotificationPreferences, UserPreferences, UserProfile
from users.services import upsert_notification_preferences, upsert_user_preferences

User = get_user_model()

JOIN_TIMEOUT = 20


class PreferenceUpsertRouteTest(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="prefs@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user)
        self.client.force_authenticate(self.user)

    def test_the_first_post_creates_the_row_and_the_second_updates_it(self):
        first = self.client.post("/api/notification-preferences/", {"transactionAlerts": False}, format="json")
        second = self.client.post("/api/notification-preferences/", {"priceAlerts": False}, format="json")

        self.assertEqual([first.status_code, second.status_code], [200, 200])
        self.assertEqual(NotificationPreferences.objects.count(), 1)
        row = NotificationPreferences.objects.get()
        self.assertFalse(row.transaction_alerts)
        self.assertFalse(row.price_alerts)

    def test_a_second_post_leaves_the_row_it_did_not_name_alone(self):
        self.client.post("/api/notification-preferences/", {"transactionAlerts": False}, format="json")
        self.client.post("/api/notification-preferences/", {"priceAlerts": False}, format="json")

        self.assertFalse(NotificationPreferences.objects.get().transaction_alerts)

    def test_the_row_belongs_to_the_caller_not_to_the_body(self):
        stranger = User.objects.create_user(email="stranger@example.test", password="pw-12345678")
        UserProfile.objects.create(user=stranger)

        self.client.post("/api/notification-preferences/", {"transactionAlerts": False}, format="json")

        self.assertEqual(NotificationPreferences.objects.get().user_profile_id, self.profile.pk)

    def test_a_caller_without_a_profile_is_not_found_rather_than_a_server_error(self):
        UserProfile.objects.filter(pk=self.profile.pk).delete()

        response = self.client.post("/api/notification-preferences/", {"transactionAlerts": False}, format="json")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(NotificationPreferences.objects.count(), 0)


@skipUnless(connection.vendor == "postgresql", "select_for_update is a no-op on SQLite")
class PreferenceUpsertConcurrencyTest(TransactionTestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="race@example.test", password="pw-12345678")
        UserProfile.objects.create(user=self.user)

    def _race(self, work):
        outcomes = {}

        def wrapped(name):
            close_old_connections()
            try:
                work(name)
                outcomes[name] = "ok"
            except Exception as error:
                outcomes[name] = f"{type(error).__name__}: {error}"
            finally:
                close_old_connections()

        threads = [threading.Thread(target=wrapped, args=(name,), name=name) for name in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=JOIN_TIMEOUT)
        self.assertFalse(any(thread.is_alive() for thread in threads), outcomes)
        return outcomes

    def test_two_concurrent_upserts_leave_exactly_one_row(self):
        outcomes = self._race(lambda name: upsert_user_preferences(self.user, {"theme": "dark"}))

        self.assertEqual(set(outcomes.values()), {"ok"}, outcomes)
        self.assertEqual(UserPreferences.objects.filter(user_profile__user=self.user).count(), 1)

    def test_two_concurrent_notification_upserts_leave_exactly_one_row(self):
        outcomes = self._race(lambda name: upsert_notification_preferences(self.user, {"transaction_alerts": False}))

        self.assertEqual(set(outcomes.values()), {"ok"}, outcomes)
        self.assertEqual(NotificationPreferences.objects.filter(user_profile__user=self.user).count(), 1)
