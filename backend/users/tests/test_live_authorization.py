from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from assets.models import Asset
from users.models import (
    FavouriteAsset,
    FinancialProfile,
    NotificationPreferences,
    UserAccount,
    UserPreferences,
    UserProfile,
)
from users.views.financial_profile import FinancialProfileViewSet
from users.views.user_account import UserAccountViewSet
from users.views.user_profile import UserProfileViewSet

User = get_user_model()


class UserLiveAuthorizationTest(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-user@example.test", password="pw-12345678")
        self.bob = User.objects.create_user(email="bob-user@example.test", password="pw-12345678")
        self.staff = User.objects.create_user(
            email="staff-user@example.test",
            password="pw-12345678",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="super-user@example.test", password="pw-12345678")
        self.alice_profile = UserProfile.objects.create(user=self.alice, full_name="Alice")
        self.bob_profile = UserProfile.objects.create(user=self.bob, full_name="Bob")
        self.alice_financial = FinancialProfile.objects.create(
            user_profile=self.alice_profile,
            occupation="Alice occupation",
        )
        self.bob_financial = FinancialProfile.objects.create(
            user_profile=self.bob_profile,
            occupation="Bob occupation",
        )
        self.alice_account = UserAccount.objects.create(account_number="ACCOUNT-ALICE")
        self.bob_account = UserAccount.objects.create(account_number="ACCOUNT-BOB")
        self.alice_account.user_profiles.add(self.alice_profile)
        self.bob_account.user_profiles.add(self.bob_profile)
        self.alice_preferences = UserPreferences.objects.create(
            user_profile=self.alice_profile,
            selected_account=self.alice_account,
        )
        self.bob_preferences = UserPreferences.objects.create(
            user_profile=self.bob_profile,
            selected_account=self.bob_account,
        )
        self.asset = Asset.objects.create(
            symbol="USER-SCOPE",
            name="User scope asset",
            asset_type="tokenized_security",
            is_active=True,
            is_verified=True,
        )
        self.alice_favourite = FavouriteAsset.objects.create(
            user_account=self.alice_account,
            asset=self.asset,
        )
        self.bob_favourite = FavouriteAsset.objects.create(
            user_account=self.bob_account,
            asset=self.asset,
        )

    @staticmethod
    def rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_profile_email_update_is_rejected_without_mutation(self):
        original_email = self.alice.email
        original_name = self.alice_profile.full_name
        self.client.force_authenticate(self.alice)

        with CaptureQueriesContext(connection) as captured:
            response = self.client.patch(
                f"/api/user-profiles/{self.alice_profile.uuid}/",
                {
                    "email": "replacement@example.test",
                    "fullName": "Updated Alice",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data,
            {"email": ["Email cannot be changed through a profile update."]},
        )
        self.alice.refresh_from_db()
        self.alice_profile.refresh_from_db()
        self.assertEqual(self.alice.email, original_email)
        self.assertEqual(self.alice_profile.full_name, original_name)
        user_table = User._meta.db_table.upper()
        self.assertFalse(
            any(
                query["sql"].lstrip().upper().startswith(f'UPDATE "{user_table}"')
                for query in captured.captured_queries
            )
        )

    def test_account_updates_preserve_membership_and_director(self):
        foreign_user = User.objects.create_user(
            email="foreign-director@example.test",
            password="pw-12345678",
        )
        foreign_profile = UserProfile.objects.create(user=foreign_user)

        self.client.force_authenticate(self.alice)
        create_response = self.client.post(
            "/api/user-accounts/",
            {
                "accountType": "joint",
                "director": foreign_profile.pk,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        joint_account = UserAccount.objects.get(uuid=create_response.json()["uuid"])
        self.assertIsNone(joint_account.director_id)
        self.assertEqual(
            set(joint_account.user_profiles.values_list("pk", flat=True)),
            {self.alice_profile.pk},
        )

        joint_account.director = self.alice_profile
        joint_account.save(update_fields=["director"])
        joint_account.user_profiles.add(self.bob_profile)
        expected_members = {self.alice_profile.pk, self.bob_profile.pk}

        self.client.force_authenticate(foreign_user)
        foreign_response = self.client.patch(
            f"/api/user-accounts/{joint_account.uuid}/",
            {"role": "company"},
            format="json",
        )
        self.assertEqual(foreign_response.status_code, 404)
        joint_account.refresh_from_db()
        self.assertEqual(joint_account.role, "investor")
        self.assertEqual(joint_account.director_id, self.alice_profile.pk)
        self.assertEqual(
            set(joint_account.user_profiles.values_list("pk", flat=True)),
            expected_members,
        )

        self.client.force_authenticate(self.alice)
        member_response = self.client.patch(
            f"/api/user-accounts/{joint_account.uuid}/",
            {"role": "both", "director": foreign_profile.pk},
            format="json",
        )
        self.assertEqual(member_response.status_code, 200)
        joint_account.refresh_from_db()
        self.assertEqual(joint_account.role, "both")
        self.assertEqual(joint_account.director_id, self.alice_profile.pk)
        self.assertEqual(
            set(joint_account.user_profiles.values_list("pk", flat=True)),
            expected_members,
        )

        for label, actor in (("staff", self.staff), ("superuser", self.superuser)):
            self.client.force_authenticate(actor)
            response = self.client.patch(
                f"/api/user-accounts/{joint_account.uuid}/",
                {"role": "company"},
                format="json",
            )

            with self.subTest(user=label):
                self.assertEqual(response.status_code, 404)
                joint_account.refresh_from_db()
                self.assertEqual(joint_account.role, "both")
                self.assertEqual(joint_account.director_id, self.alice_profile.pk)
                self.assertEqual(
                    set(joint_account.user_profiles.values_list("pk", flat=True)),
                    expected_members,
                )

    def test_update_actions_request_database_row_locks(self):
        for action in ("update", "partial_update"):
            cases = (
                (UserProfileViewSet, self.staff, ("self",)),
                (FinancialProfileViewSet, self.staff, ()),
                (UserAccountViewSet, self.alice, ()),
            )
            for view_class, user, expected_of in cases:
                view = view_class()
                view.request = SimpleNamespace(user=user)
                view.action = action

                queryset = view.get_queryset()

                with self.subTest(action=action, view=view_class.__name__):
                    self.assertTrue(queryset.query.select_for_update)
                    self.assertEqual(queryset.query.select_for_update_of, expected_of)

    def test_anonymous_managers_fail_closed(self):
        anonymous = AnonymousUser()
        by_membership = (UserAccount.objects.accounts_the_user_is_a_member_of,)
        by_live_profile = (
            FinancialProfile.objects.owned_through_the_live_profile,
            UserPreferences.objects.owned_through_the_live_profile,
            NotificationPreferences.objects.owned_through_the_live_profile,
        )
        for selector in by_membership + by_live_profile:
            with self.subTest(selector=selector.__name__, user="anonymous"):
                self.assertFalse(selector(anonymous).exists())
                self.assertFalse(selector(None).exists())
