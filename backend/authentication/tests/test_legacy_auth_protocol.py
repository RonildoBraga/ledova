import os
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from authentication.models import UserToken
from authentication.services import TokenService
from users.services import UserSetupService

User = get_user_model()

TEST_SIMPLE_JWT = {
    **settings.SIMPLE_JWT,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}


@override_settings(DEBUG=False, SIMPLE_JWT=TEST_SIMPLE_JWT)
class LegacyAuthProtocolTestCase(APITestCase):
    password = "current-password-123"

    def setUp(self):
        super().setUp()
        cookie_environment = patch.dict(
            os.environ,
            {
                "COOKIE_ACCESS_NAME": "access",
                "COOKIE_REFRESH_NAME": "refresh",
                "COOKIE_DOMAIN": "",
            },
        )
        cookie_environment.start()
        self.addCleanup(cookie_environment.stop)

    def create_user(self, email="member@example.com", verified=True):
        return User.objects.create_user(
            email=email,
            password=self.password,
            is_active=True,
            is_email_verified=verified,
        )

    def create_completed_user(self, email="member@example.com", verified=True):
        user = self.create_user(email=email, verified=verified)
        profile, _, _, _ = UserSetupService.ensure_defaults(user)
        profile.is_signup_completed = True
        profile.save(update_fields=["is_signup_completed"])
        return user

    def create_raw_user(self, email, *, password=None, active=True, verified=True):
        user = User(
            email=email,
            is_active=active,
            is_email_verified=verified,
        )
        user.set_password(password or self.password)
        user.save()
        return user

    def complete_raw_user(self, user):
        profile, _, _, _ = UserSetupService.ensure_defaults(user)
        profile.is_signup_completed = True
        profile.save(update_fields=["is_signup_completed"])
        return user

    def assert_issued_cookie(self, response, name, max_age):
        self.assertIn(name, response.cookies)
        cookie = response.cookies[name]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["max-age"], max_age)


class LegacyTransportTest(LegacyAuthProtocolTestCase):
    def test_legacy_signup_returns_safe_identity_without_starting_a_session(self):
        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {
                    "email": "New.User@Example.COM",
                    "password": self.password,
                    "passwordConfirm": self.password,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertTrue(payload["uuid"])
        self.assertEqual(payload["email"], "new.user@example.com")
        self.assertFalse(payload["isEmailVerified"])
        self.assertNotIn("password", payload)
        self.assertNotIn("passwordConfirm", payload)
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertFalse(UserToken.objects.exists())
        send_email.assert_called_once_with(User.objects.get(email="new.user@example.com"))

    def test_legacy_signin_sets_secure_httponly_cookie_pair_and_identity_fields(self):
        user = self.create_completed_user()

        response = self.client.post(
            "/api/signin/",
            {"email": user.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["uuid"], str(user.userprofile.uuid))
        self.assertEqual(payload["email"], user.email)
        self.assertTrue(payload["isEmailVerified"])
        self.assertNotIn("password", payload)
        self.assert_issued_cookie(response, "access", 900)
        self.assert_issued_cookie(response, "refresh", 604800)
        self.assertEqual(UserToken.objects.filter(user=user, is_active=True).count(), 1)

    def test_legacy_signin_resolves_one_noncanonical_stored_address(self):
        stored_email = " Legacy.Member@EXAMPLE.TEST "
        user = self.complete_raw_user(self.create_raw_user(stored_email))

        response = self.client.post(
            "/api/signin/",
            {"email": " legacy.member@example.test ", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["email"], stored_email)
        self.assertEqual(UserToken.objects.filter(user=user, is_active=True).count(), 1)

    def test_legacy_signin_absent_and_ambiguous_responses_are_identical(self):
        first = self.create_raw_user("Collision@EXAMPLE.TEST")
        second = self.create_raw_user("collision@example.test ")
        initial_state = {
            first.pk: (first.password, first.last_login),
            second.pk: (second.password, second.last_login),
        }

        absent_response = APIClient().post(
            "/api/signin/",
            {"email": "absent@example.test", "password": self.password},
            format="json",
        )
        ambiguous_response = APIClient().post(
            "/api/signin/",
            {"email": "collision@example.test", "password": self.password},
            format="json",
        )

        self.assertEqual(ambiguous_response.status_code, absent_response.status_code)
        self.assertEqual(ambiguous_response.data, absent_response.data)
        self.assertEqual(list(ambiguous_response.cookies), list(absent_response.cookies))
        self.assertFalse(UserToken.objects.exists())
        for user in (first, second):
            user.refresh_from_db()
            self.assertEqual((user.password, user.last_login), initial_state[user.pk])

    def test_legacy_signup_reuses_one_noncanonical_incomplete_account(self):
        stored_email = " Pending.Member@EXAMPLE.TEST "
        user = self.create_raw_user(stored_email, password="old-password-123", active=False, verified=False)

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {
                    "email": "pending.member@example.test",
                    "password": self.password,
                    "passwordConfirm": self.password,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["email"], stored_email)
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.password))
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0].pk, user.pk)

    def test_legacy_signup_ambiguity_fails_without_mutation_or_delivery(self):
        first = self.create_raw_user("Collision@EXAMPLE.TEST", password="first-password-123", active=False)
        second = self.create_raw_user("collision@example.test ", password="second-password-123")
        initial_state = {
            first.pk: (first.email, first.password, first.is_active),
            second.pk: (second.email, second.password, second.is_active),
        }

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {
                    "email": "collision@example.test",
                    "password": self.password,
                    "passwordConfirm": self.password,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"email": ["Email already registered"]})
        self.assertEqual(User.objects.count(), 2)
        self.assertFalse(UserToken.objects.exists())
        send_email.assert_not_called()
        for user in (first, second):
            user.refresh_from_db()
            self.assertEqual((user.email, user.password, user.is_active), initial_state[user.pk])

    def test_legacy_cookie_and_bearer_access_each_authenticate_the_verify_endpoint(self):
        user = self.create_completed_user()
        token = TokenService.create(user)

        cookie_client = APIClient()
        cookie_client.cookies["access"] = token.access_token
        cookie_response = cookie_client.get("/api/auth/verify/")

        bearer_client = APIClient()
        bearer_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        bearer_response = bearer_client.get("/api/auth/verify/")

        for response in (cookie_response, bearer_response):
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            payload = response.json()
            self.assertTrue(payload["valid"])
            self.assertTrue(payload["expiresAt"])

    def test_legacy_revoked_access_is_rejected_for_cookie_and_bearer(self):
        user = self.create_completed_user()
        token = TokenService.create(user)
        token.revoke()

        cookie_client = APIClient()
        cookie_client.cookies["access"] = token.access_token
        cookie_response = cookie_client.get("/api/auth/verify/")

        bearer_client = APIClient()
        bearer_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        bearer_response = bearer_client.get("/api/auth/verify/")

        for response in (cookie_response, bearer_response):
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json(), {"valid": False})


class LegacyRefreshLogoutTest(LegacyAuthProtocolTestCase):
    def test_legacy_refresh_requires_the_refresh_cookie(self):
        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {"error": "Refresh token not found in cookies."})
        self.assertFalse(UserToken.objects.exists())

    def test_legacy_valid_refresh_returns_one_usable_active_session(self):
        user = self.create_completed_user()
        token = TokenService.create(user)
        self.client.cookies["refresh"] = token.refresh_token

        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_issued_cookie(response, "access", 900)
        self.assert_issued_cookie(response, "refresh", 604800)
        self.assertEqual(UserToken.objects.filter(user=user, is_active=True).count(), 1)

        verify_client = APIClient()
        verify_client.cookies["access"] = response.cookies["access"].value
        verify_response = verify_client.get("/api/auth/verify/")
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.json()["valid"])

    def test_legacy_invalid_refresh_clears_both_cookie_names(self):
        self.client.cookies["refresh"] = "invalid-refresh-token"

        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.cookies["access"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh"]["max-age"], 0)
        self.assertFalse(UserToken.objects.exists())

    def test_legacy_cookie_signout_revokes_only_the_refresh_matched_session(self):
        user = self.create_completed_user()
        selected_session = TokenService.create(user)
        other_session = TokenService.create(user)
        self.client.cookies["access"] = selected_session.access_token
        self.client.cookies["refresh"] = selected_session.refresh_token

        response = self.client.post("/api/signout/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        selected_session.refresh_from_db()
        other_session.refresh_from_db()
        self.assertFalse(selected_session.is_active)
        self.assertTrue(other_session.is_active)
        self.assertEqual(response.cookies["access"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh"]["max-age"], 0)


class LegacyCredentialMutationTest(LegacyAuthProtocolTestCase):
    def test_legacy_change_password_with_correct_current_password_updates_the_hash(self):
        user = self.create_completed_user()
        token = TokenService.create(user)
        self.client.cookies["access"] = token.access_token

        response = self.client.post(
            "/api/change-password/",
            {
                "currentPassword": self.password,
                "newPassword": "replacement-password-456",
                "newPasswordConfirm": "replacement-password-456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertFalse(user.check_password(self.password))
        self.assertTrue(user.check_password("replacement-password-456"))

    def test_legacy_change_password_with_wrong_current_password_preserves_the_hash(self):
        user = self.create_completed_user()
        token = TokenService.create(user)
        self.client.cookies["access"] = token.access_token

        response = self.client.post(
            "/api/change-password/",
            {
                "currentPassword": "wrong-current-password",
                "newPassword": "replacement-password-456",
                "newPasswordConfirm": "replacement-password-456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.check_password("replacement-password-456"))

    def test_legacy_resend_for_authenticated_unverified_user_invokes_delivery(self):
        user = self.create_user(verified=False)
        token = TokenService.create(user)
        self.client.cookies["access"] = token.access_token

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post("/api/resend-verification/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        send_email.assert_called_once_with(user)

    def test_legacy_resend_rejects_an_already_verified_user_without_delivery(self):
        user = self.create_user(verified=True)
        token = TokenService.create(user)
        self.client.cookies["access"] = token.access_token

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post("/api/resend-verification/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        send_email.assert_not_called()
