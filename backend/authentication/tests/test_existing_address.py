from unittest.mock import patch

from django.contrib.auth import aauthenticate, authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import serializers

from authentication.email import EMAIL_ERROR, EmailError
from authentication.managers.user import (
    EmailLookupResult,
    EmailLookupState,
)
from authentication.models.user_token import UserToken
from authentication.serializers.user import (
    EmailVerificationSerializer,
    UserSigninSerializer,
    UserSignupSerializer,
)
from authentication.services.sessions import SessionService

User = get_user_model()


class ExistingAddressTestCase(TestCase):
    password = "current-password-123"

    def create_user(self, email, *, is_active=True, password=None):
        user = User(email=email, is_active=is_active)
        user.set_password(password or self.password)
        user.save()
        return user

    @staticmethod
    def ambiguous_result():
        return EmailLookupResult(EmailLookupState.AMBIGUOUS)


class EmailResolverTests(ExistingAddressTestCase):
    def test_zero_matches_returns_absent(self):
        with CaptureQueriesContext(connection) as captured:
            result = User.objects.resolve_email("absent@example.test")
        self.assertIs(result.state, EmailLookupState.ABSENT)
        self.assertIsNone(result.user)
        self.assertEqual(len(captured), 1)
        self.assertIn("LIMIT 2", captured[0]["sql"].upper())

    def test_one_match_returns_unique_exact_stored_user(self):
        stored_email = "legacy.owner@example.test"
        user = self.create_user(stored_email)
        result = User.objects.resolve_email("legacy.owner@example.test")
        self.assertIs(result.state, EmailLookupState.UNIQUE)
        self.assertEqual(result.user.pk, user.pk)
        self.assertEqual(result.user.email, stored_email)

    def test_two_matches_return_ambiguous_without_user(self):
        first = self.create_user("owner-one@example.test")
        second = self.create_user("owner-two@example.test")
        result = User.objects._email_result([first, second])
        self.assertIs(result.state, EmailLookupState.AMBIGUOUS)
        self.assertIsNone(result.user)

    def test_three_matches_remain_ambiguous(self):
        users = [
            self.create_user("member-one@example.test"),
            self.create_user("member-two@example.test"),
            self.create_user("member-three@example.test"),
        ]
        result = User.objects._email_result(users)
        self.assertIs(result.state, EmailLookupState.AMBIGUOUS)
        self.assertIsNone(result.user)

    def test_lookup_does_not_filter_inactive_accounts(self):
        inactive = self.create_user("state-inactive@example.test", is_active=False)
        result = User.objects.resolve_email("state-inactive@example.test")
        self.assertIs(result.state, EmailLookupState.UNIQUE)
        self.assertEqual(result.user.pk, inactive.pk)

    def test_invalid_or_noncanonical_keys_fail_without_querying(self):
        for destination_key in (
            "Owner@EXAMPLE.TEST",
            " owner@example.test ",
            "owner@example.test\t",
            "not-an-email",
        ):
            with self.subTest(destination_key=repr(destination_key)):
                with self.assertNumQueries(0), self.assertRaises(EmailError) as raised:
                    User.objects.resolve_email(destination_key)
                self.assertEqual(str(raised.exception), EMAIL_ERROR)
                self.assertNotIn(destination_key, str(raised.exception))

    def test_result_invariant_and_repr_are_redacted(self):
        user = self.create_user("private@example.test")
        result = EmailLookupResult(EmailLookupState.UNIQUE, user)
        self.assertEqual(repr(result), "EmailLookupResult(<redacted>)")
        self.assertNotIn(user.email, repr(result))
        self.assertNotIn(str(user.pk), repr(result))
        self.assertNotIn(result.state.value, repr(result))
        with self.assertRaises(ValueError):
            EmailLookupResult(EmailLookupState.UNIQUE)
        with self.assertRaises(ValueError):
            EmailLookupResult(EmailLookupState.ABSENT, user)

    def test_lookup_is_one_bounded_select_with_an_unselected_alias(self):
        self.create_user("query@example.test")
        with CaptureQueriesContext(connection) as captured:
            result = User.objects.resolve_email("query@example.test")
        self.assertIs(result.state, EmailLookupState.UNIQUE)
        self.assertEqual(len(captured), 1)
        sql = captured[0]["sql"].upper()
        self.assertTrue(sql.startswith("SELECT "))
        self.assertIn("LOWER(TRIM(", sql)
        self.assertIn("ORDER BY", sql)
        self.assertIn("LIMIT 2", sql)
        self.assertNotIn("COUNT(", sql)
        self.assertNotIn("LOWER(TRIM(", sql.split(" FROM ", 1)[0])
        for mutation in ("INSERT ", "UPDATE ", "DELETE "):
            self.assertNotIn(mutation, sql)
        if connection.vendor == "postgresql":
            self.assertIn('COLLATE "C"', sql)
        else:
            self.assertNotIn("COLLATE", sql)


class EmailSerializerBoundaryTests(ExistingAddressTestCase):
    def test_all_legacy_email_entry_points_use_the_strict_field(self):
        signin = UserSigninSerializer(
            data={"email": "member@example.test\t", "password": self.password},
        )
        verification = EmailVerificationSerializer(
            data={"email": "member@example.test\t", "token": "654321"},
        )
        signup = UserSignupSerializer(
            data={
                "email": "member@example.test\t",
                "password": self.password,
                "password_confirm": self.password,
            },
        )

        self.assertFalse(signin.is_valid())
        self.assertEqual(signin.errors, {"email": ["Enter a valid email address."]})
        self.assertFalse(verification.is_valid())
        self.assertEqual(verification.errors, {"email": ["Enter a valid email address."]})
        self.assertFalse(signup.is_valid())
        self.assertEqual(signup.errors, {"email": ["Enter a valid email address."]})


class EmailModelBackendTests(ExistingAddressTestCase):
    def test_get_by_natural_key_returns_only_a_unique_exact_row(self):
        stored_email = "legacy.login@example.test"
        user = self.create_user(stored_email)
        found = User.objects.get_by_natural_key(" Legacy.Login@EXAMPLE.TEST ")
        self.assertEqual(found.pk, user.pk)
        self.assertEqual(found.email, stored_email)

    def test_get_by_natural_key_rejects_absent_ambiguous_and_invalid(self):
        for value in ("absent@example.test", "invalid"):
            with self.subTest(value=value), self.assertRaises(User.DoesNotExist):
                User.objects.get_by_natural_key(value)

        with patch.object(
            type(User.objects),
            "resolve_email",
            return_value=self.ambiguous_result(),
        ) as resolve:
            with self.assertRaises(User.DoesNotExist):
                User.objects.get_by_natural_key("collision@example.test")
        resolve.assert_called_once_with("collision@example.test")

    def test_model_backend_runs_one_dummy_hash_for_absent_and_ambiguous(self):
        with patch("django.contrib.auth.base_user.make_password", wraps=make_password) as dummy_hash:
            self.assertIsNone(authenticate(username="absent@example.test", password=self.password))
        self.assertEqual(dummy_hash.call_count, 1)

        with (
            patch.object(
                type(User.objects),
                "resolve_email",
                return_value=self.ambiguous_result(),
            ),
            patch("django.contrib.auth.base_user.make_password", wraps=make_password) as dummy_hash,
        ):
            self.assertIsNone(authenticate(username="collision@example.test", password=self.password))
        self.assertEqual(dummy_hash.call_count, 1)

    def test_model_backend_never_checks_an_ambiguous_candidate_password(self):
        with (
            patch.object(
                type(User.objects),
                "resolve_email",
                return_value=self.ambiguous_result(),
            ),
            patch.object(User, "check_password", autospec=True) as check_password,
        ):
            self.assertIsNone(authenticate(username="collision@example.test", password=self.password))
        check_password.assert_not_called()

    def test_model_backend_preserves_password_and_active_checks(self):
        active = self.create_user("active@example.test")
        inactive = self.create_user("inactive@example.test", is_active=False)
        self.assertEqual(
            authenticate(username="active@example.test", password=self.password).pk,
            active.pk,
        )
        self.assertIsNone(authenticate(username="active@example.test", password="wrong-password"))
        self.assertIsNone(authenticate(username="inactive@example.test", password=self.password))
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)

    async def test_async_model_backend_returns_only_a_unique_active_user(self):
        active = await User.objects.acreate(
            email="async.active@example.test",
            is_active=True,
            password=make_password(self.password),
        )
        await User.objects.acreate(
            email="async.inactive@example.test",
            is_active=False,
            password=make_password(self.password),
        )

        authenticated = await aauthenticate(
            username="async.active@example.test",
            password=self.password,
        )

        self.assertEqual(authenticated.pk, active.pk)
        self.assertIsNone(
            await aauthenticate(
                username="async.inactive@example.test",
                password=self.password,
            )
        )

    async def test_async_model_backend_runs_one_dummy_hash_for_absent_and_ambiguous(self):
        with patch("django.contrib.auth.base_user.make_password", wraps=make_password) as dummy_hash:
            self.assertIsNone(
                await aauthenticate(
                    username="async.absent@example.test",
                    password=self.password,
                )
            )
        self.assertEqual(dummy_hash.call_count, 1)

        with (
            patch.object(
                type(User.objects),
                "aresolve_email",
                return_value=self.ambiguous_result(),
            ) as resolve,
            patch("django.contrib.auth.base_user.make_password", wraps=make_password) as dummy_hash,
        ):
            self.assertIsNone(
                await aauthenticate(
                    username="async.collision@example.test",
                    password=self.password,
                )
            )
        resolve.assert_awaited_once_with("async.collision@example.test")
        self.assertEqual(dummy_hash.call_count, 1)

    async def test_async_model_backend_never_checks_an_ambiguous_candidate_password(self):
        with (
            patch.object(
                type(User.objects),
                "aresolve_email",
                return_value=self.ambiguous_result(),
            ),
            patch.object(User, "acheck_password", autospec=True) as check_password,
        ):
            self.assertIsNone(
                await aauthenticate(
                    username="async.collision@example.test",
                    password=self.password,
                )
            )
        check_password.assert_not_awaited()


class EmailSignupLookupTests(ExistingAddressTestCase):
    def create_users(self):
        first = self.create_user(
            "signup-first@example.test",
            password="first-password-123",
            is_active=False,
        )
        second = self.create_user(
            "signup-second@example.test",
            password="second-password-123",
        )
        return first, second

    def assert_users_unchanged(self, users, initial_state):
        self.assertEqual(User.objects.count(), 2)
        self.assertFalse(UserToken.objects.exists())
        for user in users:
            user.refresh_from_db()
            self.assertEqual(
                (user.email, user.password, user.is_active),
                initial_state[user.pk],
            )

    def test_signup_rejects_ambiguity_before_mutation(self):
        users = self.create_users()
        initial_state = {user.pk: (user.email, user.password, user.is_active) for user in users}
        with (
            patch.object(
                type(User.objects),
                "resolve_email",
                return_value=self.ambiguous_result(),
            ) as resolve,
            self.assertRaises(serializers.ValidationError) as raised,
        ):
            SessionService.signup("signup@example.test", self.password, self.password)
        self.assertEqual(raised.exception.detail, {"email": ["Email already registered"]})
        resolve.assert_called_once_with("signup@example.test")
        self.assert_users_unchanged(users, initial_state)
