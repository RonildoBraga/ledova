from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from rest_framework.test import APITransactionTestCase

from shared.tests.scoped import RunsOnTheScopedConnection
from users.models import UserAccount, UserProfile

POSTGRES = connection.vendor == "postgresql"
REASON = "the alias split and its policies exist only in PostgreSQL"
User = get_user_model()


@skipUnless(POSTGRES, REASON)
class ChoosingAnAccountTypeUnderTheAppRoleTest(RunsOnTheScopedConnection, APITransactionTestCase):

    def setUp(self):
        with self.as_an_operator_would():
            self.user = User.objects.create_user(email="type@example.test", password="pw-12345678", is_active=True)
            self.profile = UserProfile.objects.create(user=self.user, is_signup_completed=True)
            self.account = UserAccount.objects.create(account_number="ACC-TYPE", director=self.profile)
            self.account.user_profiles.add(self.profile)
        self.signed_in_as(self.user)

    def test_the_suite_is_running_on_the_scoped_connection_so_the_assertion_below_means_something(self):
        self.assertEqual(settings.RLS_AMBIENT_ALIAS, "app")

    def test_choosing_an_account_type_is_not_refused_by_the_connection_it_runs_on(self):
        url = reverse("user-accounts-detail", args=[self.account.uuid])

        response = self.client.patch(url, {"account_type": "individual"}, format="json")

        self.assertEqual(response.status_code, 200, getattr(response, "data", response))
