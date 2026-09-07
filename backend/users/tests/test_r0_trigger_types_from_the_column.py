from unittest import skipUnless

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase, TransactionTestCase

from shared.models import Country
from shared.tests.schema import migrate_to, restore_every_migration
from users.admin.user_profile import UserProfileAdmin
from users.models import NotificationPreferences, UserPreferences, UserProfile

User = get_user_model()
POSTGRES = connection.vendor == "postgresql"
REASON = "the trigger is PostgreSQL only, and on SQLite there is nothing to declare a type in"

BEYOND_A_SIGNED_INTEGER = 2**31 + 1


def _country():
    country, _ = Country.objects.get_or_create(code="TST", defaults={"name": "Type country"})
    return country


@skipUnless(POSTGRES, REASON)
class TheTriggerHoldsAUserKeyOfAnySizeTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            id=BEYOND_A_SIGNED_INTEGER,
            email="big@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
        )
        self.profile = UserProfile.objects.create(user=self.user, full_name="Big Id", citizenship_country=_country())

    def test_a_preferences_row_derives_its_owner_from_a_bigint_user_key(self):
        preferences = UserPreferences.objects.create(user_profile=self.profile)

        preferences.refresh_from_db()
        self.assertEqual(preferences.user_id, BEYOND_A_SIGNED_INTEGER)

    def test_every_table_the_function_serves_holds_the_same_key(self):
        notifications = NotificationPreferences.objects.create(user_profile=self.profile)

        notifications.refresh_from_db()
        self.assertEqual(notifications.user_id, BEYOND_A_SIGNED_INTEGER)

    def test_the_declaration_names_no_type_of_its_own(self):
        self.assertIn("users_userprofile.user_id%TYPE", _definition())
        self.assertNotIn("parent_user_id integer", _definition())


def _definition(function="users_userpreferences_user_is_derived"):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef(%s::regproc)", [function])
        return cursor.fetchone()[0]


@skipUnless(POSTGRES, REASON)
class AProfileThatMovesLeavesItsRowsWorkingTest(TestCase):

    def setUp(self):
        self.first = User.objects.create_user(email="first@example.test", password="pw-12345678", is_active=True)
        self.second = User.objects.create_user(email="second@example.test", password="pw-12345678", is_active=True)
        self.profile = UserProfile.objects.create(user=self.first, full_name="Mover", citizenship_country=_country())
        self.preferences = UserPreferences.objects.create(user_profile=self.profile)

    def move_the_profile(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(user=self.second)

    def test_an_ordinary_write_after_the_profile_moves_is_not_refused(self):
        self.move_the_profile()

        UserPreferences.objects.filter(pk=self.preferences.pk).update(selected_account=None)

        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.user_id, self.second.pk)

    def test_moving_the_column_to_someone_the_profile_does_not_name_is_refused(self):
        with self.assertRaises(Exception) as refusal:
            UserPreferences.objects.filter(pk=self.preferences.pk).update(user=self.second)

        self.assertIn("cannot be moved to", str(refusal.exception))

    def test_following_the_parent_is_allowed(self):
        self.move_the_profile()

        UserPreferences.objects.filter(pk=self.preferences.pk).update(user=self.second)

        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.user_id, self.second.pk)


@skipUnless(POSTGRES, REASON)
class TheInstalledBodyIsTheAmendedOneTest(TestCase):

    def test_the_forward_installs_the_branch_that_follows_the_parent(self):
        definition = _definition()

        self.assertIn("IS NOT DISTINCT FROM OLD.user_id", definition)
        self.assertIn("user_profile_id cannot change, from", definition)
        self.assertNotIn("user_id cannot change, from", definition)


@skipUnless(POSTGRES, REASON)
class TheRoundTripRestoresWhatWasThereTest(TransactionTestCase):

    def tearDown(self):
        restore_every_migration()
        super().tearDown()

    def test_the_reverse_puts_back_the_body_0020_installed_and_the_forward_amends_it_again(self):
        migrate_to([("users", "0020_r0_owner_columns")])
        reversed_body = _definition()

        self.assertIn("parent_user_id integer;", reversed_body)
        self.assertIn("user_id cannot change, from", reversed_body)
        self.assertNotIn("IS NOT DISTINCT FROM OLD.user_id", reversed_body)
        self.assertNotIn("user_profile_id cannot change", reversed_body)

        migrate_to([("users", "0021_trigger_types_from_the_column")])
        forward_body = _definition()

        self.assertIn("users_userprofile.user_id%TYPE", forward_body)
        self.assertIn("IS NOT DISTINCT FROM OLD.user_id", forward_body)
        self.assertIn("user_profile_id cannot change, from", forward_body)
        self.assertNotIn("user_id cannot change, from", forward_body)


class TheProfileOwnerIsSetOnceTest(TestCase):

    def setUp(self):
        self.admin = UserProfileAdmin(UserProfile, AdminSite())
        self.request = RequestFactory().get("/admin/")

    def test_the_add_form_still_asks_for_the_user(self):
        self.assertNotIn("user", self.admin.get_readonly_fields(self.request, None))

    def test_the_change_form_will_not_move_it(self):
        user = User.objects.create_user(email="once@example.test", password="pw-12345678", is_active=True)
        profile = UserProfile.objects.create(user=user, full_name="Once", citizenship_country=_country())

        self.assertIn("user", self.admin.get_readonly_fields(self.request, profile))
