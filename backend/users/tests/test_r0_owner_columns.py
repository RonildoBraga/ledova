from django.contrib.auth import get_user_model
from django.db import IntegrityError, ProgrammingError, connection, transaction
from django.test import TestCase

from users.models import (
    FinancialProfile,
    NotificationPreferences,
    UserPreferences,
    UserProfile,
)

User = get_user_model()

POSTGRES_ONLY = (
    "The derive-and-refuse trigger is PostgreSQL only: SQLite has no plpgsql, and the column exists "
    "for a PostgreSQL row-level security policy, so there is nothing on SQLite for it to protect."
)

ROWS = (
    (NotificationPreferences, {}),
    (UserPreferences, {}),
    (FinancialProfile, {}),
)


def a_user(email):
    user = User.objects.create_user(email=email, password="pw-12345678")
    return user, UserProfile.objects.create(user=user)


class OwnerColumnIsDerivedInPythonTest(TestCase):

    def setUp(self):
        self.user, self.profile = a_user("owner@example.test")

    def test_every_row_carries_its_profiles_user_without_being_told(self):
        for model, extra in ROWS:
            with self.subTest(model=model.__name__):
                row = model.objects.create(user_profile=self.profile, **extra)

                self.assertEqual(row.user_id, self.user.pk)

    def test_get_or_create_fills_the_column_too(self):
        row, created = NotificationPreferences.objects.get_or_create(user_profile=self.profile)

        self.assertTrue(created)
        self.assertEqual(row.user_id, self.user.pk)

    def test_an_explicit_owner_is_left_alone(self):
        row = FinancialProfile.objects.create(user_profile=self.profile, user=self.user)

        self.assertEqual(row.user_id, self.user.pk)

    def test_the_column_is_not_in_the_api_representation(self):
        from users.serializers.financial_profile import FinancialProfileSerializer
        from users.serializers.notification_preferences import (
            NotificationPreferencesSerializer,
        )
        from users.serializers.user_preferences import UserPreferencesSerializer

        for serializer in (FinancialProfileSerializer, NotificationPreferencesSerializer, UserPreferencesSerializer):
            with self.subTest(serializer=serializer.__name__):
                self.assertNotIn("user", serializer().fields)


class OwnerColumnTriggerTest(TestCase):

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest(POSTGRES_ONLY)
        self.user, self.profile = a_user("triggered@example.test")
        self.stranger, self.stranger_profile = a_user("stranger@example.test")

    def _bulk_insert(self, model, user):
        row = model(user_profile=self.profile, user=user)
        model.objects.bulk_create([row])
        return model.objects.get(pk=row.pk)

    def test_bulk_create_bypasses_the_python_half_and_the_trigger_derives(self):
        for model, _ in ROWS:
            with self.subTest(model=model.__name__):
                stored = self._bulk_insert(model, None)

                self.assertEqual(stored.user_id, self.user.pk)
                stored.delete()

    def test_a_mismatched_owner_is_refused(self):
        for model, _ in ROWS:
            with self.subTest(model=model.__name__):
                with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
                    with transaction.atomic():
                        self._bulk_insert(model, self.stranger)

                self.assertIn("does not match user_profile.user_id", str(raised.exception))

    def test_the_owner_cannot_be_changed_after_the_row_exists(self):
        for model, extra in ROWS:
            with self.subTest(model=model.__name__):
                row = model.objects.create(user_profile=self.profile, **extra)
                table = model._meta.db_table

                with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{table}" SET user_id = %s WHERE uuid = %s',
                            [self.stranger.pk, row.pk],
                        )

                self.assertIn("does not match user_profile.user_id", str(raised.exception))
                row.delete()

    def test_moving_a_row_to_another_users_profile_is_refused(self):
        for model, extra in ROWS:
            with self.subTest(model=model.__name__):
                row = model.objects.create(user_profile=self.profile, **extra)
                table = model._meta.db_table

                with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{table}" SET user_profile_id = %s WHERE uuid = %s',
                            [self.stranger_profile.pk, row.pk],
                        )

                self.assertIn("does not match user_profile.user_id", str(raised.exception))
                row.delete()

    def test_changing_the_profile_and_the_owner_together_is_still_refused(self):
        for model, extra in ROWS:
            with self.subTest(model=model.__name__):
                row = model.objects.create(user_profile=self.profile, **extra)
                table = model._meta.db_table

                with self.assertRaises((IntegrityError, ProgrammingError)) as raised:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE "{table}" SET user_profile_id = %s, user_id = %s WHERE uuid = %s',
                            [self.stranger_profile.pk, self.stranger.pk, row.pk],
                        )

                self.assertIn("user_id cannot change", str(raised.exception))
                row.delete()

    def test_nulling_the_owner_is_repaired_rather_than_refused(self):
        for model, extra in ROWS:
            with self.subTest(model=model.__name__):
                row = model.objects.create(user_profile=self.profile, **extra)
                table = model._meta.db_table

                with connection.cursor() as cursor:
                    cursor.execute(f'UPDATE "{table}" SET user_id = NULL WHERE uuid = %s', [row.pk])

                row.refresh_from_db()
                self.assertEqual(row.user_id, self.user.pk)
                row.delete()

    def test_an_ordinary_update_still_works(self):
        row = UserPreferences.objects.create(user_profile=self.profile)

        row.theme = "light"
        row.save(update_fields=["theme"])
        row.refresh_from_db()

        self.assertEqual(row.theme, "light")
        self.assertEqual(row.user_id, self.user.pk)
