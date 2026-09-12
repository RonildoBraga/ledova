from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings

from shared.db import use_operator
from shared.db.principal import (
    give_the_role_back,
    take_the_app_role,
    the_app_role_is_taken,
    the_owner_for_a_moment,
)
from users.models import UserProfile

User = get_user_model()

POSTGRES = connection.vendor == "postgresql"
REASON = "a role is a PostgreSQL thing; on SQLite every assertion here would pass without a role existing"


def current_role():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        return cursor.fetchone()[0]


@skipUnless(POSTGRES, REASON)
@override_settings(RLS_ROLE_PER_REQUEST=True)
class TakingTheScopedRoleOnOneConnectionTest(TestCase):

    def tearDown(self):
        give_the_role_back()

    def test_the_role_changes_and_comes_back(self):
        owner = current_role()

        take_the_app_role()
        self.assertEqual(current_role(), settings.RLS_ROLES["app"])
        self.assertNotEqual(current_role(), owner)

        give_the_role_back()
        self.assertEqual(current_role(), owner)

    def test_the_operator_context_drops_the_role_for_its_body_only(self):
        owner = current_role()
        take_the_app_role()

        with use_operator():
            inside = current_role()

        self.assertEqual(inside, owner)
        self.assertEqual(current_role(), settings.RLS_ROLES["app"])

    def test_the_operator_context_leaves_an_untaken_role_alone(self):
        owner = current_role()

        with the_owner_for_a_moment():
            self.assertEqual(current_role(), owner)

        self.assertEqual(current_role(), owner)
        self.assertFalse(the_app_role_is_taken())

    def test_nesting_the_operator_context_still_ends_scoped(self):
        take_the_app_role()

        with use_operator():
            with use_operator():
                pass

        self.assertEqual(current_role(), settings.RLS_ROLES["app"])


@skipUnless(POSTGRES, REASON)
@override_settings(RLS_ROLE_PER_REQUEST=False)
class TheSettingIsWhatTurnsItOnTest(TestCase):

    def test_nothing_happens_while_the_setting_is_off(self):
        owner = current_role()

        take_the_app_role()

        self.assertEqual(current_role(), owner)
        self.assertFalse(the_app_role_is_taken())


@skipUnless(POSTGRES, REASON)
@override_settings(RLS_ROLE_PER_REQUEST=True)
class ThePoliciesActuallyApplyTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.mine = User.objects.create_user(email="rls-mine@example.test", password="pw-12345678")
        cls.theirs = User.objects.create_user(email="rls-theirs@example.test", password="pw-12345678")
        UserProfile.objects.create(user=cls.mine, full_name="Mine")
        UserProfile.objects.create(user=cls.theirs, full_name="Theirs")

    def tearDown(self):
        give_the_role_back()

    def profiles_visible(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM users_userprofile")
            return cursor.fetchone()[0]

    def test_the_owner_sees_both_profiles(self):
        self.assertEqual(self.profiles_visible(), 2)

    def test_the_scoped_role_with_a_principal_sees_only_its_own(self):
        take_the_app_role()
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.user_id', %s, false)", [str(self.mine.pk)])

        self.assertEqual(self.profiles_visible(), 1)

    def test_the_scoped_role_without_a_principal_sees_nothing(self):
        take_the_app_role()

        self.assertEqual(self.profiles_visible(), 0)
