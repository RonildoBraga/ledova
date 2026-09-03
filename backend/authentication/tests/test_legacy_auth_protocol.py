from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from authentication.managers.user import EmailLookupResult, EmailLookupState
from authentication.services import TokenService
from users.services import UserSetupService

User = get_user_model()

TEST_SIMPLE_JWT = {
    **settings.SIMPLE_JWT,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

TEST_AUTH_COOKIE = {"access": "access", "refresh": "refresh", "domain": None, "secure": True, "samesite": "Lax"}

IDENTITY_KEYS = {"uuid", "email", "isEmailVerified"}


def jti_of(raw_refresh):
    return RefreshToken(raw_refresh, verify=False)["jti"]


def is_blacklisted(raw_refresh):
    return BlacklistedToken.objects.filter(token__jti=jti_of(raw_refresh)).exists()


@override_settings(DEBUG=False, SIMPLE_JWT=TEST_SIMPLE_JWT, AUTH_COOKIE=TEST_AUTH_COOKIE)
class LegacyAuthProtocolTestCase(APITestCase):
    password = "current-password-123"

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

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

    def create_direct_user(self, email, *, password=None, active=True, verified=True):
        user = User(
            email=email,
            is_active=active,
            is_email_verified=verified,
        )
        user.set_password(password or self.password)
        user.save()
        return user

    def complete_direct_user(self, user):
        profile, _, _, _ = UserSetupService.ensure_defaults(user)
        profile.is_signup_completed = True
        profile.save(update_fields=["is_signup_completed"])
        return user

    @staticmethod
    def ambiguous_email_result():
        return EmailLookupResult(EmailLookupState.AMBIGUOUS)

    def assert_issued_cookie(self, response, name, max_age):
        self.assertIn(name, response.cookies)
        cookie = response.cookies[name]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["max-age"], max_age)

    def assert_session_body(self, response, user):
        """The mobile app reads `tokens[0].accessToken/refreshToken`; the pair must be the one in the cookies."""
        payload = response.json()
        self.assertEqual(set(payload), IDENTITY_KEYS | {"tokens"})
        self.assertEqual(payload["email"], user.email)
        self.assertEqual(len(payload["tokens"]), 1)
        self.assertEqual(set(payload["tokens"][0]), {"accessToken", "refreshToken"})
        self.assertEqual(payload["tokens"][0]["accessToken"], response.cookies["access"].value)
        self.assertEqual(payload["tokens"][0]["refreshToken"], response.cookies["refresh"].value)
        self.assertEqual(response["Cache-Control"], "no-store")
        return payload

    def verify_with_cookie(self, access_token):
        client = APIClient()
        client.cookies["access"] = access_token
        return client.get("/api/auth/verify/").json()

    def verify_with_bearer(self, access_token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client.get("/api/auth/verify/").json()


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
        self.assertEqual(set(payload), IDENTITY_KEYS)
        self.assertTrue(payload["uuid"])
        self.assertEqual(payload["email"], "new.user@example.com")
        self.assertFalse(payload["isEmailVerified"])
        self.assertNotIn("access", response.cookies)
        self.assertNotIn("refresh", response.cookies)
        self.assertFalse(OutstandingToken.objects.exists())
        send_email.assert_called_once_with(User.objects.get(email="new.user@example.com"))

    def test_legacy_signup_rejects_noncanonical_raw_input_without_side_effects(self):
        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {
                    "email": "new.user@example.com\t",
                    "password": self.password,
                    "passwordConfirm": self.password,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"email": ["Enter a valid email address."]})
        self.assertFalse(User.objects.exists())
        self.assertFalse(OutstandingToken.objects.exists())
        send_email.assert_not_called()

    def test_legacy_signin_sets_secure_httponly_cookie_pair_and_identity_fields(self):
        user = self.create_completed_user()

        response = self.client.post(
            "/api/signin/",
            {"email": user.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = self.assert_session_body(response, user)
        self.assertEqual(payload["uuid"], str(user.userprofile.uuid))
        self.assertTrue(payload["isEmailVerified"])
        self.assert_issued_cookie(response, "access", 900)
        self.assert_issued_cookie(response, "refresh", 604800)
        self.assertEqual(OutstandingToken.objects.filter(user=user).count(), 1)
        self.assertFalse(BlacklistedToken.objects.exists())
        self.assertTrue(self.verify_with_cookie(payload["tokens"][0]["accessToken"])["valid"])

    def test_legacy_signin_issues_its_own_session_and_discloses_no_other(self):
        user = self.create_completed_user()
        other_access, other_refresh = TokenService.issue(user)

        response = self.client.post(
            "/api/signin/",
            {"email": user.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = self.assert_session_body(response, user)
        self.assertNotIn(other_access, str(payload))
        self.assertNotIn(other_refresh, str(payload))
        self.assertEqual(OutstandingToken.objects.filter(user=user).count(), 2)
        self.assertTrue(self.verify_with_cookie(other_access)["valid"])

    def test_legacy_signin_normalizes_input_for_a_canonical_stored_address(self):
        stored_email = "legacy.member@example.test"
        user = self.complete_direct_user(self.create_direct_user(stored_email))

        response = self.client.post(
            "/api/signin/",
            {"email": " Legacy.Member@EXAMPLE.TEST ", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["email"], stored_email)
        self.assertEqual(OutstandingToken.objects.filter(user=user).count(), 1)

    def test_legacy_signin_absent_and_ambiguous_responses_are_identical(self):
        first = self.create_direct_user("collision-first@example.test")
        second = self.create_direct_user("collision-second@example.test")
        initial_state = {
            first.pk: (first.password, first.last_login),
            second.pk: (second.password, second.last_login),
        }

        absent_response = APIClient().post(
            "/api/signin/",
            {"email": "absent@example.test", "password": self.password},
            format="json",
        )
        with patch.object(
            type(User.objects),
            "resolve_email",
            return_value=self.ambiguous_email_result(),
        ) as resolve:
            ambiguous_response = APIClient().post(
                "/api/signin/",
                {"email": "collision@example.test", "password": self.password},
                format="json",
            )

        self.assertEqual(ambiguous_response.status_code, absent_response.status_code)
        self.assertEqual(ambiguous_response.data, absent_response.data)
        self.assertEqual(list(ambiguous_response.cookies), list(absent_response.cookies))
        resolve.assert_called_once_with("collision@example.test")
        self.assertFalse(OutstandingToken.objects.exists())
        for user in (first, second):
            user.refresh_from_db()
            self.assertEqual((user.password, user.last_login), initial_state[user.pk])

    def test_legacy_signup_for_an_incomplete_account_never_overwrites_the_password(self):
        stored_email = "pending.member@example.test"
        user = self.create_direct_user(
            stored_email,
            password="old-password-123",
            active=False,
            verified=False,
        )
        stored_hash = user.password

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {
                    "email": " Pending.Member@EXAMPLE.TEST ",
                    "password": self.password,
                    "passwordConfirm": self.password,
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.json()), IDENTITY_KEYS)
        self.assertEqual(response.json()["email"], stored_email)
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.password, stored_hash)
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password("old-password-123"))
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0].pk, user.pk)

    def test_legacy_signup_with_the_matching_password_resends_the_code_untouched(self):
        user = self.create_direct_user("pending.member@example.test", active=True, verified=False)
        stored_hash = user.password

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post(
                "/api/signup/",
                {"email": user.email, "password": self.password, "passwordConfirm": self.password},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.password, stored_hash)
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0].pk, user.pk)

    def test_legacy_signup_ambiguity_fails_without_mutation_or_delivery(self):
        first = self.create_direct_user(
            "collision-first@example.test",
            password="first-password-123",
            active=False,
        )
        second = self.create_direct_user(
            "collision-second@example.test",
            password="second-password-123",
        )
        initial_state = {
            first.pk: (first.email, first.password, first.is_active),
            second.pk: (second.email, second.password, second.is_active),
        }

        with (
            patch("authentication.views.user.EmailCodeService.send") as send_email,
            patch.object(
                type(User.objects),
                "resolve_email",
                return_value=self.ambiguous_email_result(),
            ) as resolve,
        ):
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
        self.assertFalse(OutstandingToken.objects.exists())
        resolve.assert_called_once_with("collision@example.test")
        send_email.assert_not_called()
        for user in (first, second):
            user.refresh_from_db()
            self.assertEqual((user.email, user.password, user.is_active), initial_state[user.pk])

    def test_legacy_cookie_and_bearer_access_each_authenticate_the_verify_endpoint(self):
        user = self.create_completed_user()
        access, _ = TokenService.issue(user)

        for payload in (self.verify_with_cookie(access), self.verify_with_bearer(access)):
            self.assertEqual(set(payload), {"valid", "expiresAt"})
            self.assertTrue(payload["valid"])
            self.assertTrue(payload["expiresAt"])

    def test_legacy_revoked_access_is_rejected_for_cookie_and_bearer(self):
        user = self.create_completed_user()
        access, refresh = TokenService.issue(user)
        TokenService.revoke(refresh)

        self.assertTrue(is_blacklisted(refresh))
        self.assertEqual(self.verify_with_cookie(access), {"valid": False})
        self.assertEqual(self.verify_with_bearer(access), {"valid": False})

    def test_legacy_access_token_without_a_live_refresh_session_is_rejected(self):
        user = self.create_completed_user()
        unbound = str(AccessToken.for_user(user))
        orphan = RefreshToken.for_user(user)
        orphan_access = orphan.access_token
        orphan_access["rjti"] = orphan["jti"]
        OutstandingToken.objects.filter(jti=orphan["jti"]).delete()

        self.assertEqual(self.verify_with_cookie(unbound), {"valid": False})
        self.assertEqual(self.verify_with_cookie(str(orphan_access)), {"valid": False})

    def test_legacy_revoke_all_invalidates_every_issued_access_token(self):
        user = self.create_completed_user()
        first_access, first_refresh = TokenService.issue(user)
        second_access, second_refresh = TokenService.issue(user)
        TokenService.revoke(first_refresh)

        TokenService.revoke_all(user)

        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        self.assertEqual(self.verify_with_cookie(first_access), {"valid": False})
        self.assertEqual(self.verify_with_cookie(second_access), {"valid": False})
        self.assertFalse(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).exists())


class LegacyRefreshLogoutTest(LegacyAuthProtocolTestCase):
    def test_legacy_refresh_requires_a_refresh_token(self):
        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {"error": "Refresh token not found."})
        self.assertFalse(OutstandingToken.objects.exists())

    def test_legacy_cookie_refresh_rotates_and_retires_the_presented_token(self):
        user = self.create_completed_user()
        old_access, old_refresh = TokenService.issue(user)
        self.client.cookies["refresh"] = old_refresh

        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.json()), {"access", "refresh"})
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assert_issued_cookie(response, "access", 900)
        self.assert_issued_cookie(response, "refresh", 604800)
        new_access, new_refresh = response.json()["access"], response.json()["refresh"]
        self.assertEqual(
            (response.cookies["access"].value, response.cookies["refresh"].value), (new_access, new_refresh)
        )
        self.assertNotEqual(jti_of(old_refresh), jti_of(new_refresh))
        self.assertTrue(is_blacklisted(old_refresh))
        self.assertFalse(is_blacklisted(new_refresh))
        self.assertEqual(OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count(), 1)
        self.assertTrue(self.verify_with_cookie(new_access)["valid"])
        self.assertEqual(self.verify_with_cookie(old_access), {"valid": False})

        self.client.cookies["refresh"] = old_refresh
        replay = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(replay.cookies["access"]["max-age"], 0)
        self.assertEqual(replay.cookies["refresh"]["max-age"], 0)

    def test_legacy_body_refresh_rotates_for_cookieless_clients(self):
        user = self.create_completed_user()
        _, old_refresh = TokenService.issue(user)

        response = self.client.post("/api/token/refresh/", {"refresh": old_refresh}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.json()), {"access", "refresh"})
        self.assertTrue(is_blacklisted(old_refresh))
        self.assertTrue(self.verify_with_bearer(response.json()["access"])["valid"])

        second = self.client.post("/api/token/refresh/", {"refresh": response.json()["refresh"]}, format="json")

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertNotEqual(jti_of(second.json()["refresh"]), jti_of(response.json()["refresh"]))

    def test_legacy_invalid_refresh_clears_both_cookie_names(self):
        self.client.cookies["refresh"] = "invalid-refresh-token"

        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json(), {"error": "Invalid refresh token."})
        self.assertEqual(response.cookies["access"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh"]["max-age"], 0)
        self.assertFalse(OutstandingToken.objects.exists())

    def test_legacy_refresh_for_a_disabled_user_is_rejected(self):
        user = self.create_completed_user()
        _, refresh = TokenService.issue(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.client.cookies["refresh"] = refresh

        response = self.client.post("/api/token/refresh/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(OutstandingToken.objects.filter(user=user).count(), 1)

    def test_legacy_cookie_signout_revokes_only_the_refresh_matched_session(self):
        user = self.create_completed_user()
        selected_access, selected_refresh = TokenService.issue(user)
        other_access, other_refresh = TokenService.issue(user)
        self.client.cookies["access"] = selected_access
        self.client.cookies["refresh"] = selected_refresh

        response = self.client.post("/api/signout/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"message": "Successfully signed out."})
        self.assertTrue(is_blacklisted(selected_refresh))
        self.assertFalse(is_blacklisted(other_refresh))
        self.assertEqual(self.verify_with_cookie(selected_access), {"valid": False})
        self.assertTrue(self.verify_with_cookie(other_access)["valid"])
        self.assertEqual(response.cookies["access"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh"]["max-age"], 0)

    def test_legacy_bearer_signout_without_a_refresh_revokes_only_its_own_session(self):
        user = self.create_completed_user()
        mobile_access, mobile_refresh = TokenService.issue(user)
        dashboard_access, dashboard_refresh = TokenService.issue(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {mobile_access}")

        response = self.client.post("/api/signout/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(is_blacklisted(mobile_refresh))
        self.assertFalse(is_blacklisted(dashboard_refresh))
        self.assertEqual(self.verify_with_bearer(mobile_access), {"valid": False})
        self.assertTrue(self.verify_with_cookie(dashboard_access)["valid"])

    def test_legacy_body_refresh_signout_revokes_that_session(self):
        user = self.create_completed_user()
        access, refresh = TokenService.issue(user)
        _, other_refresh = TokenService.issue(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.post("/api/signout/", {"refresh": refresh}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(is_blacklisted(refresh))
        self.assertFalse(is_blacklisted(other_refresh))

    def test_legacy_anonymous_signout_clears_cookies_without_touching_sessions(self):
        user = self.create_completed_user()
        _, refresh = TokenService.issue(user)

        response = self.client.post("/api/signout/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.cookies["access"]["max-age"], 0)
        self.assertFalse(is_blacklisted(refresh))

    def test_legacy_signout_all_revokes_every_session_and_requires_authentication(self):
        user = self.create_completed_user()
        first_access, first_refresh = TokenService.issue(user)
        second_access, second_refresh = TokenService.issue(user)
        bystander = self.create_completed_user(email="bystander@example.com")
        _, bystander_refresh = TokenService.issue(bystander)

        anonymous = APIClient().post("/api/signout-all/", {}, format="json")
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.cookies["access"] = first_access
        response = self.client.post("/api/signout-all/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"message": "Successfully signed out."})
        self.assertEqual(response.cookies["access"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh"]["max-age"], 0)
        self.assertTrue(is_blacklisted(first_refresh))
        self.assertTrue(is_blacklisted(second_refresh))
        self.assertFalse(is_blacklisted(bystander_refresh))
        self.assertEqual(self.verify_with_cookie(first_access), {"valid": False})
        self.assertEqual(self.verify_with_cookie(second_access), {"valid": False})


class TokenLifetimeDefaultsTest(SimpleTestCase):
    def test_access_lives_a_day_and_refresh_a_week_by_default(self):
        self.assertEqual(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], timedelta(days=1))
        self.assertEqual(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"], timedelta(days=7))


class CookieSettingsTest(LegacyAuthProtocolTestCase):
    custom_cookie = {"access": "sid", "refresh": "rid", "domain": "example.test", "secure": False, "samesite": "Lax"}

    @override_settings(AUTH_COOKIE=custom_cookie)
    def test_cookie_names_domain_and_secure_flag_come_from_auth_cookie(self):
        user = self.create_completed_user()

        response = self.client.post("/api/signin/", {"email": user.email, "password": self.password}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.cookies), {"sid", "rid"})
        for name in ("sid", "rid"):
            self.assertEqual(response.cookies[name]["domain"], "example.test")
            self.assertFalse(response.cookies[name]["secure"])
            self.assertTrue(response.cookies[name]["httponly"])
            self.assertEqual(response.cookies[name]["samesite"], "Lax")

        client = APIClient()
        client.cookies["sid"] = response.cookies["sid"].value
        self.assertTrue(client.get("/api/auth/verify/").json()["valid"])

        client.cookies["rid"] = response.cookies["rid"].value
        signout = client.post("/api/signout/", {}, format="json")
        self.assertEqual(signout.status_code, status.HTTP_200_OK)
        self.assertEqual(set(signout.cookies), {"sid", "rid"})
        for name in ("sid", "rid"):
            self.assertEqual(signout.cookies[name]["max-age"], 0)
            self.assertEqual(signout.cookies[name]["domain"], "example.test")


class EmailThrottleTest(LegacyAuthProtocolTestCase):
    def signin(self, email, password="wrong-password"):
        return self.client.post("/api/signin/", {"email": email, "password": password}, format="json")

    def test_eleventh_signin_for_one_address_within_an_hour_is_throttled(self):
        user = self.create_completed_user()

        for _ in range(9):
            self.assertEqual(self.signin(user.email).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.signin(" Member@EXAMPLE.com ").status_code, status.HTTP_400_BAD_REQUEST)

        throttled = self.signin(user.email, self.password)

        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertNotIn("access", throttled.cookies)
        self.assertFalse(OutstandingToken.objects.exists())
        self.assertEqual(self.signin("other@example.com").status_code, status.HTTP_400_BAD_REQUEST)

    def test_signup_and_verification_share_the_address_budget(self):
        with patch("authentication.views.user.EmailCodeService.send"):
            for _ in range(5):
                response = self.client.post(
                    "/api/signup/",
                    {"email": "new@example.com", "password": self.password, "passwordConfirm": self.password},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for _ in range(5):
            response = self.client.post(
                "/api/email-verification/", {"email": "new@example.com", "token": "111111"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            "/api/email-verification/", {"email": "new@example.com", "token": "111111"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_resend_is_throttled_per_authenticated_address(self):
        user = self.create_user(verified=False)
        access, _ = TokenService.issue(user)
        self.client.cookies["access"] = access

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            for _ in range(10):
                self.assertEqual(
                    self.client.post("/api/resend-verification/", {}, format="json").status_code, status.HTTP_200_OK
                )
            throttled = self.client.post("/api/resend-verification/", {}, format="json")

        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(send_email.call_count, 10)

    def test_refresh_and_signout_are_not_address_throttled(self):
        user = self.create_completed_user()
        for _ in range(10):
            self.assertEqual(self.signin(user.email).status_code, status.HTTP_400_BAD_REQUEST)
        _, refresh = TokenService.issue(user)
        self.client.cookies["refresh"] = refresh

        self.assertEqual(self.client.post("/api/token/refresh/", {}, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post("/api/signout/", {}, format="json").status_code, status.HTTP_200_OK)


class LegacyCredentialMutationTest(LegacyAuthProtocolTestCase):
    def test_legacy_change_password_with_correct_current_password_updates_the_hash(self):
        user = self.create_completed_user()
        access, _ = TokenService.issue(user)
        self.client.cookies["access"] = access

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
        access, _ = TokenService.issue(user)
        self.client.cookies["access"] = access

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
        access, _ = TokenService.issue(user)
        self.client.cookies["access"] = access

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post("/api/resend-verification/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        send_email.assert_called_once_with(user)

    def test_legacy_resend_rejects_an_already_verified_user_without_delivery(self):
        user = self.create_user(verified=True)
        access, _ = TokenService.issue(user)
        self.client.cookies["access"] = access

        with patch("authentication.views.user.EmailCodeService.send") as send_email:
            response = self.client.post("/api/resend-verification/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        send_email.assert_not_called()
