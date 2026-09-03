import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from authentication.managers.user import EmailLookupResult, EmailLookupState
from authentication.services.email_codes import (
    CODE_LIFETIME,
    MAX_ATTEMPTS,
    EmailCodeService,
    _digest,
)
from authentication.services.tokens import TokenService

User = get_user_model()

SESSION_KEYS = {"uuid", "email", "isEmailVerified", "tokens"}


@override_settings(DEBUG=False)
class EmailVerificationTest(APITestCase):
    endpoint = "/api/email-verification/"
    invalid_response = {"token": ["Invalid email or verification code."]}

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    @staticmethod
    def issue_code(user, code="654321", sent_at=None):
        """Store a code the way EmailCodeService.send does, without sending mail."""
        user.email_verification_token = _digest(user, code)
        user.email_verification_sent_at = sent_at or timezone.now()
        user.email_verification_attempts = 0
        user.save()
        return user

    def create_pending_user(self, email="pending@example.com", code="654321", sent_at=None):
        user = User.objects.create_user(email=email, password="testpass123", is_active=True)
        return self.issue_code(user, code, sent_at)

    def create_direct_user(self, email, code="654321"):
        user = User(email=email, is_active=True)
        user.set_password("testpass123")
        user.save()
        return self.issue_code(user, code)

    def post_code(self, email, code):
        return self.client.post(self.endpoint, {"email": email, "token": code}, format="json")

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, self.invalid_response)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)

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
        user = self.create_pending_user()

        response = self.post_code(user.email, "123456")

        self.assert_rejected(response)
        self.assertFalse(OutstandingToken.objects.filter(user=user).exists())
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.email_verification_token, _digest(user, "654321"))
        self.assertEqual(user.email_verification_attempts, 1)

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
        user = self.create_pending_user()

        response = self.post_code(user.email, "654321")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.cookies)
        self.assertIn("refresh", response.cookies)
        payload = response.json()
        self.assertEqual(set(payload), SESSION_KEYS)
        self.assertTrue(payload["isEmailVerified"])
        self.assertEqual(payload["tokens"][0]["accessToken"], response.cookies["access"].value)
        self.assertEqual(payload["tokens"][0]["refreshToken"], response.cookies["refresh"].value)
        self.assertEqual(response["Cache-Control"], "no-store")
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.email_verification_token)
        self.assertEqual(user.email_verification_attempts, 0)
        self.assertEqual(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count(), 1)

        replay_response = self.post_code(user.email, "654321")

        self.assert_rejected(replay_response)
        self.assertEqual(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count(), 1)

    @override_settings(SENDGRID_API_KEY="")
    def test_send_stores_only_a_hash_and_mails_the_code(self):
        user = User.objects.create_user(email="fresh@example.com", password="testpass123", is_active=True)

        self.assertTrue(EmailCodeService.send(user))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        user.refresh_from_db()
        candidates = set(re.findall(r"(?<!\d)\d{6}(?!\d)", mail.outbox[0].body))
        codes = [code for code in candidates if _digest(user, code) == user.email_verification_token]
        self.assertEqual(len(codes), 1)
        self.assertNotIn(codes[0], user.email_verification_token)
        self.assertEqual(len(user.email_verification_token), 64)
        self.assertIsNotNone(user.email_verification_sent_at)
        self.assertEqual(user.email_verification_attempts, 0)

        response = self.post_code(user.email, codes[0])

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_expired_code_is_rejected_and_left_untouched(self):
        user = self.create_pending_user(sent_at=timezone.now() - CODE_LIFETIME - timedelta(seconds=1))

        response = self.post_code(user.email, "654321")

        self.assert_rejected(response)
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.email_verification_attempts, 0)
        self.assertFalse(OutstandingToken.objects.exists())

    def test_code_without_a_sent_timestamp_is_rejected(self):
        user = self.create_pending_user()
        user.email_verification_sent_at = None
        user.save(update_fields=["email_verification_sent_at"])

        self.assert_rejected(self.post_code(user.email, "654321"))

    def test_last_failed_attempt_clears_the_code(self):
        user = self.create_pending_user()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.assert_rejected(self.post_code(user.email, "000001"))
            user.refresh_from_db()
            self.assertEqual(user.email_verification_attempts, attempt)
        self.assertIsNone(user.email_verification_token)

        self.assert_rejected(self.post_code(user.email, "654321"))
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)
        self.assertFalse(OutstandingToken.objects.exists())

    @override_settings(DEBUG=True)
    def test_the_old_debug_bypass_code_is_rejected(self):
        with_code = self.create_pending_user(email="with-code@example.com")
        without_code = User.objects.create_user(email="no-code@example.com", password="testpass123", is_active=True)

        for user in (with_code, without_code):
            self.assert_rejected(self.post_code(user.email, "000000"))
            user.refresh_from_db()
            self.assertFalse(user.is_email_verified)
        self.assertFalse(OutstandingToken.objects.exists())

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
            self.assertEqual(user.email_verification_token, _digest(user, "654321"))
            self.assertEqual(user.email_verification_attempts, 0)
