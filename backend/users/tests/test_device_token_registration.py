from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import DeviceToken

User = get_user_model()

PUSH_TOKEN = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"


class DeviceTokenRegistrationTest(APITestCase):

    def setUp(self):
        self.owner = self._user("device-owner")
        self.other = self._user("device-other")

    def _user(self, label):
        return User.objects.create_user(
            email=f"{label}@example.test", password="pw-12345678", is_active=True, is_email_verified=True
        )

    def _register(self, user, push_token=PUSH_TOKEN, device_type="ios"):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/device-tokens/register/",
            {"pushToken": push_token, "deviceType": device_type},
            format="json",
        )

    def test_a_first_registration_creates_the_row(self):
        response = self._register(self.owner)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(DeviceToken.objects.get(push_token=PUSH_TOKEN).user, self.owner)

    def test_registering_the_same_token_again_updates_rather_than_duplicating(self):
        self._register(self.owner)

        response = self._register(self.owner, device_type="android")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DeviceToken.objects.filter(push_token=PUSH_TOKEN).count(), 1)
        self.assertEqual(DeviceToken.objects.get(push_token=PUSH_TOKEN).device_type, "android")

    def test_another_user_registering_the_same_token_takes_the_device_over(self):
        self._register(self.owner)

        response = self._register(self.other)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DeviceToken.objects.get(push_token=PUSH_TOKEN).user, self.other)
