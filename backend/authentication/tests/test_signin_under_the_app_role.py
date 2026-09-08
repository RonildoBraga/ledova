from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from shared.db.principal import PRINCIPAL_SETTING
from users.models import UserProfile

POSTGRES = connection.vendor == "postgresql"
REASON = "the policy that blinds the profile lookup exists only in PostgreSQL"

SIGNIN = reverse("auth-signin")
SIGNUP = reverse("auth-signup")
PASSWORD = "pw-12345678"
User = get_user_model()


@skipUnless(POSTGRES, REASON)
class SigningInUnderTheAppRoleWithNoPrincipalTest(TransactionTestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="signin@example.test", password=PASSWORD, is_active=True)
        UserProfile.objects.update_or_create(user=self.user, defaults={"is_signup_completed": True})
        self.client = APIClient()
        self.addCleanup(self.back_to_the_owner)
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")

    def back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])

    def test_the_role_really_is_scoped_and_blind_so_the_assertion_below_means_something(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone()[0], settings.RLS_ROLES["app"])
            cursor.execute(f"SELECT NULLIF(current_setting('{PRINCIPAL_SETTING}', true), '') IS NULL")
            self.assertTrue(cursor.fetchone()[0])
            cursor.execute("SELECT count(*) FROM users_userprofile")
            self.assertEqual(
                cursor.fetchone()[0], 0, "the profile is visible without a principal, so nothing is proved"
            )

    def test_a_completed_account_signs_in_rather_than_being_told_to_finish_signing_up(self):
        response = self.client.post(SIGNIN, {"email": "signin@example.test", "password": PASSWORD}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("complete your signup", str(response.data))

    def test_a_wrong_password_is_still_refused_and_no_principal_is_taken_for_it(self):
        response = self.client.post(SIGNIN, {"email": "signin@example.test", "password": "wrong-one"}, format="json")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Invalid email or password", str(response.data))
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT NULLIF(current_setting('{PRINCIPAL_SETTING}', true), '') IS NULL")
            self.assertTrue(cursor.fetchone()[0], "a refused sign-in took a principal anyway")


@skipUnless(POSTGRES, REASON)
class SigningUpUnderTheAppRoleWithNoPrincipalTest(TransactionTestCase):

    def setUp(self):
        self.client = APIClient()
        self.addCleanup(self.back_to_the_owner)
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")

    def back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])

    def a_registered_account(self, email):
        self.back_to_the_owner()
        user = User.objects.create_user(email=email, password=PASSWORD, is_active=True)
        UserProfile.objects.update_or_create(user=user, defaults={"is_signup_completed": True})
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
        return user

    def signup(self, email, **overrides):
        body = {"email": email, "password": PASSWORD, "password_confirm": PASSWORD}
        body.update(overrides)
        return self.client.post(SIGNUP, body, format="json")

    def test_the_role_really_is_scoped_and_blind_so_the_assertions_below_mean_something(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone()[0], settings.RLS_ROLES["app"])
            cursor.execute(f"SELECT NULLIF(current_setting('{PRINCIPAL_SETTING}', true), '') IS NULL")
            self.assertTrue(cursor.fetchone()[0])

    def test_a_new_email_creates_the_account_and_its_profile(self):
        response = self.signup("fresh@example.test")

        self.assertEqual(response.status_code, 201, response.data)
        self.back_to_the_owner()
        user = User.objects.get(email="fresh@example.test")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_an_email_already_registered_hits_the_guard_rather_than_the_write_policy(self):
        self.a_registered_account("taken@example.test")

        response = self.signup("taken@example.test")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Email already registered", str(response.data))

    def test_a_mismatched_confirmation_is_still_refused_before_any_row_is_written(self):
        response = self.signup("mismatch@example.test", password_confirm="something-else")

        self.assertEqual(response.status_code, 400, response.data)
        self.back_to_the_owner()
        self.assertFalse(User.objects.filter(email="mismatch@example.test").exists())
