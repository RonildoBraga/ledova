from unittest.mock import patch

from django.contrib.auth import aauthenticate, authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import serializers

from authentication.managers.user import (
    V2EmailLookupResult,
    V2EmailLookupState,
)
from authentication.models.user_token import UserToken
from authentication.security.v2_email import V2_EMAIL_ERROR, V2EmailError
from authentication.serializers.user import (
    EmailVerificationSerializer,
    UserSigninSerializer,
    UserSignupSerializer,
)
from authentication.services.sessions import SessionService

User = get_user_model()


class V2ExistingAddressTestCase(TestCase):
    password = "current-password-123"

    def create_raw_user(self, email, *, is_active=True, password=None):
        user = User(email=email, is_active=is_active)
        user.set_password(password or self.password)
        user.save()
        return user


class V2EmailResolverTests(V2ExistingAddressTestCase):
    def test_zero_matches_returns_absent(self):
        with CaptureQueriesContext(connection) as captured:
            result = User.objects.resolve_v2_email("absent@example.test")
        self.assertIs(result.state, V2EmailLookupState.ABSENT)
        self.assertIsNone(result.user)
        self.assertEqual(len(captured), 1)
        self.assertIn("LIMIT 2", captured[0]["sql"].upper())

    def test_one_match_returns_unique_exact_stored_user(self):
        stored_email = " Legacy.Owner@EXAMPLE.TEST "
        user = self.create_raw_user(stored_email)
        result = User.objects.resolve_v2_email("legacy.owner@example.test")
        self.assertIs(result.state, V2EmailLookupState.UNIQUE)
        self.assertEqual(result.user.pk, user.pk)
        self.assertEqual(result.user.email, stored_email)

    def test_two_matches_return_ambiguous_without_user(self):
        self.create_raw_user("Owner@EXAMPLE.TEST")
        self.create_raw_user(" owner@example.test ")
        with CaptureQueriesContext(connection) as captured:
            result = User.objects.resolve_v2_email("owner@example.test")
        self.assertIs(result.state, V2EmailLookupState.AMBIGUOUS)
        self.assertIsNone(result.user)
        self.assertEqual(len(captured), 1)
        self.assertIn("LIMIT 2", captured[0]["sql"].upper())

    def test_three_matches_remain_bounded_and_ambiguous(self):
        self.create_raw_user("Member@EXAMPLE.TEST")
        self.create_raw_user(" member@example.test")
        self.create_raw_user("member@example.test ")
        with CaptureQueriesContext(connection) as captured:
            result = User.objects.resolve_v2_email("member@example.test")
        self.assertIs(result.state, V2EmailLookupState.AMBIGUOUS)
        self.assertEqual(len(captured), 1)
        self.assertIn("LIMIT 2", captured[0]["sql"].upper())

    def test_account_state_does_not_change_cardinality(self):
        self.create_raw_user("State@EXAMPLE.TEST", is_active=True)
        self.create_raw_user("state@example.test ", is_active=False)
        result = User.objects.resolve_v2_email("state@example.test")
        self.assertIs(result.state, V2EmailLookupState.AMBIGUOUS)

    def test_invalid_or_noncanonical_keys_fail_without_querying(self):
        for destination_key in (
            "Owner@EXAMPLE.TEST",
            " owner@example.test ",
            "owner@example.test\t",
            "not-an-email",
        ):
            with self.subTest(destination_key=repr(destination_key)):
                with self.assertNumQueries(0), self.assertRaises(V2EmailError) as raised:
                    User.objects.resolve_v2_email(destination_key)
                self.assertEqual(str(raised.exception), V2_EMAIL_ERROR)
                self.assertNotIn(destination_key, str(raised.exception))

    def test_result_invariant_and_repr_are_redacted(self):
        user = self.create_raw_user("private@example.test")
        result = V2EmailLookupResult(V2EmailLookupState.UNIQUE, user)
        self.assertEqual(repr(result), "V2EmailLookupResult(<redacted>)")
        self.assertNotIn(user.email, repr(result))
        self.assertNotIn(str(user.pk), repr(result))
        self.assertNotIn(result.state.value, repr(result))
        with self.assertRaises(ValueError):
            V2EmailLookupResult(V2EmailLookupState.UNIQUE)
        with self.assertRaises(ValueError):
            V2EmailLookupResult(V2EmailLookupState.ABSENT, user)

    def test_lookup_is_one_bounded_select_with_an_unselected_alias(self):
        self.create_raw_user("Query@EXAMPLE.TEST")
        with CaptureQueriesContext(connection) as captured:
            result = User.objects.resolve_v2_email("query@example.test")
        self.assertIs(result.state, V2EmailLookupState.UNIQUE)
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


class V2EmailSerializerBoundaryTests(V2ExistingAddressTestCase):
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


class V2EmailModelBackendTests(V2ExistingAddressTestCase):
    def test_get_by_natural_key_returns_only_a_unique_exact_row(self):
        stored_email = " Legacy.Login@EXAMPLE.TEST "
        user = self.create_raw_user(stored_email)
        found = User.objects.get_by_natural_key(" legacy.login@example.test ")
        self.assertEqual(found.pk, user.pk)
        self.assertEqual(found.email, stored_email)

    def test_get_by_natural_key_rejects_absent_ambiguous_and_invalid(self):
        self.create_raw_user("Collision@EXAMPLE.TEST")
        self.create_raw_user("collision@example.test ")
        for value in ("absent@example.test", "collision@example.test", "invalid"):
            with self.subTest(value=value), self.assertRaises(User.DoesNotExist):
                User.objects.get_by_natural_key(value)

    def test_model_backend_runs_one_dummy_hash_for_absent_and_ambiguous(self):
        self.create_raw_user("Collision@EXAMPLE.TEST")
        self.create_raw_user("collision@example.test ")
        for value in ("absent@example.test", "collision@example.test"):
            with self.subTest(value=value):
                with patch("django.contrib.auth.base_user.make_password", wraps=make_password) as dummy_hash:
                    self.assertIsNone(authenticate(username=value, password=self.password))
                self.assertEqual(dummy_hash.call_count, 1)

    def test_model_backend_never_checks_an_ambiguous_candidate_password(self):
        self.create_raw_user("Collision@EXAMPLE.TEST")
        self.create_raw_user("collision@example.test ")
        with patch.object(User, "check_password", autospec=True) as check_password:
            self.assertIsNone(authenticate(username="collision@example.test", password=self.password))
        check_password.assert_not_called()

    def test_model_backend_preserves_password_and_active_checks(self):
        active = self.create_raw_user(" Active@EXAMPLE.TEST ")
        inactive = self.create_raw_user(" Inactive@EXAMPLE.TEST ", is_active=False)
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
            email=" Async.Active@EXAMPLE.TEST ",
            is_active=True,
            password=make_password(self.password),
        )
        await User.objects.acreate(
            email=" Async.Inactive@EXAMPLE.TEST ",
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
        await User.objects.acreate(
            email="Async.Collision@EXAMPLE.TEST",
            password=make_password(self.password),
        )
        await User.objects.acreate(
            email="async.collision@example.test ",
            password=make_password(self.password),
        )

        for value in ("async.absent@example.test", "async.collision@example.test"):
            with self.subTest(value=value):
                with patch("django.contrib.auth.base_user.make_password", wraps=make_password) as dummy_hash:
                    self.assertIsNone(await aauthenticate(username=value, password=self.password))
                self.assertEqual(dummy_hash.call_count, 1)

    async def test_async_model_backend_never_checks_an_ambiguous_candidate_password(self):
        await User.objects.acreate(
            email="Async.Collision@EXAMPLE.TEST",
            password=make_password(self.password),
        )
        await User.objects.acreate(
            email="async.collision@example.test ",
            password=make_password(self.password),
        )

        with patch.object(User, "acheck_password", autospec=True) as check_password:
            self.assertIsNone(
                await aauthenticate(
                    username="async.collision@example.test",
                    password=self.password,
                )
            )
        check_password.assert_not_awaited()


class V2EmailSignupLookupTests(V2ExistingAddressTestCase):
    def create_collision(self):
        first = self.create_raw_user("Signup@EXAMPLE.TEST", password="first-password-123", is_active=False)
        second = self.create_raw_user("signup@example.test ", password="second-password-123")
        return first, second

    def assert_collision_unchanged(self, users, initial_state):
        self.assertEqual(User.objects.count(), 2)
        self.assertFalse(UserToken.objects.exists())
        for user in users:
            user.refresh_from_db()
            self.assertEqual(
                (user.email, user.password, user.is_active),
                initial_state[user.pk],
            )

    def test_signup_with_token_rejects_ambiguity_before_mutation(self):
        users = self.create_collision()
        initial_state = {user.pk: (user.email, user.password, user.is_active) for user in users}
        with self.assertRaises(serializers.ValidationError) as raised:
            SessionService.signup(
                "signup@example.test",
                self.password,
                self.password,
            )
        self.assertEqual(raised.exception.detail, {"email": ["Email already registered"]})
        self.assert_collision_unchanged(users, initial_state)

    def test_signup_without_token_rejects_ambiguity_before_mutation(self):
        users = self.create_collision()
        initial_state = {user.pk: (user.email, user.password, user.is_active) for user in users}
        with self.assertRaises(serializers.ValidationError) as raised:
            SessionService.signup_without_token(
                "signup@example.test",
                self.password,
                self.password,
            )
        self.assertEqual(raised.exception.detail, {"email": ["Email already registered"]})
        self.assert_collision_unchanged(users, initial_state)
