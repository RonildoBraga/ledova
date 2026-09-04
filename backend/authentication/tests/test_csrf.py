from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from authentication.services import TokenService
from authentication.services.email_codes import EmailCodeService
from users.services import ensure_defaults

User = get_user_model()

PASSWORD = "current-password-123"
NEW_PASSWORD = "replacement-password-456"
CHANGE_PASSWORD_BODY = {
    "currentPassword": PASSWORD,
    "newPassword": NEW_PASSWORD,
    "newPasswordConfirm": NEW_PASSWORD,
}
DASHBOARD_ORIGIN = "http://localhost:5174"


def create_member(verified=True):
    user = User.objects.create_user(
        email="member@example.com", password=PASSWORD, is_active=True, is_email_verified=verified
    )
    profile, _, _, _ = ensure_defaults(user)
    profile.is_signup_completed = True
    profile.save(update_fields=["is_signup_completed"])
    return user


class CookieTransportCsrfTest(APITestCase):
    """Browser-style requests: the cookie is sent automatically, so unsafe methods need the CSRF token."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = create_member()
        self.access, _ = TokenService.issue(self.user)
        self.client = APIClient(enforce_csrf_checks=True)

    def cookie_client(self):
        self.client.cookies["access"] = self.access
        return self.client

    def csrf_token(self):
        self.client.get("/api/auth/verify/")
        return self.client.cookies["csrftoken"].value

    def assert_password_unchanged(self):
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_cookie_post_without_csrf_header_is_rejected_without_state_change(self):
        response = self.cookie_client().post("/api/change-password/", CHANGE_PASSWORD_BODY, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.json()["detail"].startswith("CSRF Failed"))
        self.assert_password_unchanged()

    def test_cookie_post_with_mismatched_csrf_header_is_rejected(self):
        client = self.cookie_client()
        self.csrf_token()

        response = client.post(
            "/api/change-password/", CHANGE_PASSWORD_BODY, format="json", HTTP_X_CSRFTOKEN="not-the-token"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.json()["detail"].startswith("CSRF Failed"))
        self.assert_password_unchanged()

    def test_cookie_post_with_matching_csrf_cookie_and_header_succeeds(self):
        client = self.cookie_client()
        token = self.csrf_token()

        response = client.post("/api/change-password/", CHANGE_PASSWORD_BODY, format="json", HTTP_X_CSRFTOKEN=token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    @override_settings(CSRF_TRUSTED_ORIGINS=[DASHBOARD_ORIGIN])
    def test_cross_origin_cookie_post_is_accepted_only_from_a_trusted_origin(self):
        client = self.cookie_client()
        token = self.csrf_token()

        untrusted = client.post(
            "/api/change-password/",
            CHANGE_PASSWORD_BODY,
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="http://evil.example",
        )
        self.assertEqual(untrusted.status_code, status.HTTP_403_FORBIDDEN)
        self.assert_password_unchanged()

        trusted = client.post(
            "/api/change-password/",
            CHANGE_PASSWORD_BODY,
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN=DASHBOARD_ORIGIN,
        )
        self.assertEqual(trusted.status_code, status.HTTP_200_OK)

    def test_cookie_get_needs_no_csrf_token(self):
        response = self.cookie_client().get("/api/auth/verify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["valid"])

    def test_bearer_post_without_csrf_header_succeeds(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

        response = self.client.post("/api/change-password/", CHANGE_PASSWORD_BODY, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_anonymous_post_is_denied_as_unauthenticated_not_as_csrf(self):
        response = self.client.post("/api/change-password/", CHANGE_PASSWORD_BODY, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class BearerBesideCookieTest(APITestCase):
    """React Native's cookie jar replays the access cookie set at sign-in next to the mobile app's
    Bearer token, so the header must win: no CSRF check, and a stale cookie must not shadow it."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = create_member()
        self.access, _ = TokenService.issue(self.user)
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def assert_password_changed(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_bearer_with_matching_access_cookie_needs_no_csrf_header(self):
        self.client.cookies["access"] = self.access

        response = self.client.post("/api/change-password/", CHANGE_PASSWORD_BODY, format="json")

        self.assert_password_changed(response)

    def test_bearer_is_not_shadowed_by_a_revoked_access_cookie(self):
        stale_access, stale_refresh = TokenService.issue(self.user)
        TokenService.revoke(stale_refresh)
        self.client.cookies["access"] = stale_access

        verify = self.client.get("/api/auth/verify/")
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        self.assertTrue(verify.json()["valid"])

        response = self.client.post("/api/change-password/", CHANGE_PASSWORD_BODY, format="json")

        self.assert_password_changed(response)


class CsrfCookieBootstrapTest(APITestCase):
    """The dashboard needs a readable csrftoken cookie on load (verify) and with every issued session."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient(enforce_csrf_checks=True)

    def assert_readable_csrf_cookie(self, response):
        cookie = response.cookies["csrftoken"]
        self.assertTrue(cookie.value)
        self.assertFalse(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        return cookie

    def test_anonymous_verify_sets_the_csrf_cookie(self):
        response = self.client.get("/api/auth/verify/")

        self.assertEqual(response.json(), {"valid": False})
        self.assert_readable_csrf_cookie(response)

    def test_signin_sets_the_csrf_cookie_with_the_auth_cookies(self):
        create_member()

        response = self.client.post(
            "/api/signin/", {"email": "member@example.com", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue({"access", "refresh", "csrftoken"} <= set(response.cookies))
        self.assert_readable_csrf_cookie(response)

    def test_email_verification_sets_the_csrf_cookie_with_the_auth_cookies(self):
        user = create_member(verified=False)

        with patch.object(EmailCodeService, "verify", return_value=True):
            response = self.client.post(
                "/api/email-verification/", {"email": user.email, "token": "123456"}, format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.cookies)
        self.assert_readable_csrf_cookie(response)

    @override_settings(
        AUTH_COOKIE={
            "access": "access",
            "refresh": "refresh",
            "domain": "example.test",
            "secure": True,
            "samesite": "Lax",
        },
        CSRF_COOKIE_DOMAIN="example.test",
        CSRF_COOKIE_SECURE=True,
    )
    def test_csrf_cookie_shares_the_auth_cookie_scope(self):
        create_member()

        response = self.client.post(
            "/api/signin/", {"email": "member@example.com", "password": PASSWORD}, format="json"
        )

        for name in ("access", "csrftoken"):
            self.assertEqual(response.cookies[name]["domain"], "example.test")
            self.assertTrue(response.cookies[name]["secure"])
