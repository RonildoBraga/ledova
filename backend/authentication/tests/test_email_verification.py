from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.models.user_token import UserToken
from authentication.services.tokens import TokenService

User = get_user_model()


@override_settings(DEBUG=False)
class EmailVerificationTest(APITestCase):
    endpoint = "/api/email-verification/"
    invalid_response = {"token": ["Invalid email or verification code."]}

    def test_wrong_code_cannot_disclose_or_reuse_an_existing_session(self):
        user = User.objects.create_user(
            email="verified@example.com",
            password="testpass123",
            is_active=True,
            is_email_verified=True,
        )
        existing_token = TokenService.create(user)

        response = self.client.post(
            self.endpoint,
            {"email": user.email, "token": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.invalid_response)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertNotIn(existing_token.access_token, str(response.data))
        self.assertNotIn(existing_token.refresh_token, str(response.data))
        self.assertEqual(UserToken.objects.filter(user=user).count(), 1)
        existing_token.refresh_from_db()
        self.assertTrue(existing_token.is_active)

    def test_wrong_code_does_not_change_user_or_create_session(self):
        user = User.objects.create_user(
            email="pending@example.com",
            password="testpass123",
            is_active=True,
            email_verification_token="654321",
        )

        response = self.client.post(
            self.endpoint,
            {"email": user.email, "token": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.invalid_response)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertFalse(UserToken.objects.filter(user=user).exists())
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.email_verification_token, "654321")

    def test_unknown_email_uses_the_same_failure_response(self):
        response = self.client.post(
            self.endpoint,
            {"email": "unknown@example.com", "token": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.invalid_response)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertFalse(UserToken.objects.exists())

    def test_missing_email_is_rejected_without_creating_a_session(self):
        response = self.client.post(
            self.endpoint,
            {"token": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertFalse(UserToken.objects.exists())

    def test_valid_code_creates_one_session_and_cannot_be_replayed(self):
        user = User.objects.create_user(
            email="pending@example.com",
            password="testpass123",
            is_active=True,
            email_verification_token="654321",
        )

        response = self.client.post(
            self.endpoint,
            {"email": user.email, "token": "654321"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.cookies)
        self.assertIn("refresh", response.cookies)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_token)
        self.assertEqual(UserToken.objects.filter(user=user, is_active=True).count(), 1)

        replay_response = self.client.post(
            self.endpoint,
            {"email": user.email, "token": "654321"},
            format="json",
        )

        self.assertEqual(replay_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(replay_response.data, self.invalid_response)
        self.assertNotIn("access", replay_response.cookies)
        self.assertNotIn("refresh", replay_response.cookies)
        self.assertEqual(UserToken.objects.filter(user=user, is_active=True).count(), 1)
