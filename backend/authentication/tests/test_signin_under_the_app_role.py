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
