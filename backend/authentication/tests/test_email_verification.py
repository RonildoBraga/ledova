from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from authentication.managers.user import EmailLookupResult, EmailLookupState
from authentication.services.tokens import TokenService

User = get_user_model()


@override_settings(DEBUG=False)
class EmailVerificationTest(APITestCase):
    endpoint = "/api/email-verification/"
    invalid_response = {"token": ["Invalid email or verification code."]}

    def create_direct_user(self, email, token="654321"):
        user = User(
            email=email,
            is_active=True,
            email_verification_token=token,
        )
        user.set_password("testpass123")
        user.save()
        return user

    def test_wrong_code_cannot_disclose_or_reuse_an_existing_session(self):
        user = User.objects.create_user(
            email="verified@example.com",
            password="testpass123",
            is_active=True,
            is_email_verified=True,
        )
        existing_access, existing_refresh = TokenService.issue(user)

        response = self.client.post(
            self.endpoint,
            {"email": user.email, "token": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.invalid_response)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertNotIn(existing_access, str(response.data))
        self.assertNotIn(existing_refresh, str(response.data))
        self.assertEqual(OutstandingToken.objects.filter(user=user).count(), 1)
        self.assertFalse(BlacklistedToken.objects.exists())

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
        self.assertFalse(OutstandingToken.objects.filter(user=user).exists())
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
        self.assertFalse(OutstandingToken.objects.exists())

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
        self.assertFalse(OutstandingToken.objects.exists())

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
        payload = response.json()
        self.assertEqual(set(payload), {"uuid", "email", "isEmailVerified", "isPhoneVerified", "tokens"})
        self.assertEqual(payload["tokens"][0]["accessToken"], response.cookies["access"].value)
        self.assertEqual(payload["tokens"][0]["refreshToken"], response.cookies["refresh"].value)
        self.assertEqual(response["Cache-Control"], "no-store")
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_token)
        self.assertEqual(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count(), 1)

        replay_response = self.client.post(
            self.endpoint,
            {"email": user.email, "token": "654321"},
            format="json",
        )

        self.assertEqual(replay_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(replay_response.data, self.invalid_response)
        self.assertNotIn("access", replay_response.cookies)
        self.assertNotIn("refresh", replay_response.cookies)
        self.assertEqual(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count(), 1)

    def test_canonical_stored_address_is_verified_from_normalized_input(self):
        stored_email = "pending.member@example.test"
        user = self.create_direct_user(stored_email)

        response = self.client.post(
            self.endpoint,
            {"email": " Pending.Member@EXAMPLE.TEST ", "token": "654321"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["email"], stored_email)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_token)
        self.assertEqual(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count(), 1)

    def test_absent_and_ambiguous_destinations_have_the_same_failure(self):
        first = self.create_direct_user("pending-first@example.test")
        second = self.create_direct_user("pending-second@example.test")

        absent_response = self.client.post(
            self.endpoint,
            {"email": "absent@example.test", "token": "654321"},
            format="json",
        )
        with patch.object(
            type(User.objects),
            "resolve_email",
            return_value=EmailLookupResult(EmailLookupState.AMBIGUOUS),
        ) as resolve:
            ambiguous_response = self.client.post(
                self.endpoint,
                {"email": "pending@example.test", "token": "654321"},
                format="json",
            )

        self.assertEqual(ambiguous_response.status_code, absent_response.status_code)
        self.assertEqual(ambiguous_response.data, absent_response.data)
        self.assertEqual(list(ambiguous_response.cookies), list(absent_response.cookies))
        resolve.assert_called_once_with("pending@example.test")
        self.assertFalse(OutstandingToken.objects.exists())
        for user in (first, second):
            user.refresh_from_db()
            self.assertFalse(user.is_email_verified)
            self.assertEqual(user.email_verification_token, "654321")
