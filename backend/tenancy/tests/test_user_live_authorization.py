"""Application-level user-data isolation through live ownership relationships."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from guardian.shortcuts import assign_perm, remove_perm
from rest_framework.test import APITestCase

from assets.models import Asset
from users.models import (
    FavouriteAsset,
    FinancialProfile,
    UserAccount,
    UserPreferences,
    UserProfile,
)

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
        self.superuser = User.objects.create_user(
            email="super-user@example.test",
            password="pw-12345678",
            is_superuser=True,
        )
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

    def grant_alice_bob_permissions(self):
        for permission, instance in (
            ("users.view_userprofile", self.bob_profile),
            ("users.view_financialprofile", self.bob_financial),
            ("users.view_userpreferences", self.bob_preferences),
            ("users.view_favouriteasset", self.bob_favourite),
        ):
            assign_perm(permission, self.alice, instance)

    def remove_alice_view_permissions(self):
        for permission, instance in (
            ("users.view_userprofile", self.alice_profile),
            ("users.view_financialprofile", self.alice_financial),
            ("users.view_userpreferences", self.alice_preferences),
            ("users.view_favouriteasset", self.alice_favourite),
        ):
            remove_perm(permission, self.alice, instance)

    def test_live_scopes_ignore_stale_and_missing_guardian_grants(self):
        self.grant_alice_bob_permissions()
        self.remove_alice_view_permissions()

        cases = (
            (UserProfile.objects.visible_to_user(self.alice), self.alice_profile, self.bob_profile),
            (
                FinancialProfile.objects.visible_to_user(self.alice),
                self.alice_financial,
                self.bob_financial,
            ),
            (
                UserPreferences.objects.visible_to_user(self.alice),
                self.alice_preferences,
                self.bob_preferences,
            ),
            (
                FavouriteAsset.objects.visible_to_user(self.alice),
                self.alice_favourite,
                self.bob_favourite,
            ),
        )
        for queryset, own_object, foreign_object in cases:
            with self.subTest(model=queryset.model._meta.label):
                self.assertIn(own_object, queryset)
                self.assertNotIn(foreign_object, queryset)

    def test_profile_reassignment_immediately_updates_profile_and_financial_visibility(self):
        replacement_owner = User.objects.create_user(
            email="replacement-user@example.test",
            password="pw-12345678",
        )

        self.alice_profile.user = replacement_owner
        self.alice_profile.save(update_fields=["user"])

        self.assertNotIn(self.alice_profile, UserProfile.objects.visible_to_user(self.alice))
        self.assertNotIn(self.alice_financial, FinancialProfile.objects.visible_to_user(self.alice))
        self.assertIn(self.alice_profile, UserProfile.objects.visible_to_user(replacement_owner))
        self.assertIn(self.alice_financial, FinancialProfile.objects.visible_to_user(replacement_owner))

    def test_account_membership_immediately_controls_favourite_access(self):
        self.alice_account.user_profiles.remove(self.alice_profile)

        self.assertNotIn(self.alice_favourite, FavouriteAsset.objects.visible_to_user(self.alice))
        self.client.force_authenticate(self.alice)
        own_url = f"/api/favourite-assets/{self.alice_favourite.uuid}/"
        self.assertEqual(self.client.get(own_url).status_code, 404)
        self.assertEqual(self.client.delete(own_url).status_code, 404)
        self.assertTrue(FavouriteAsset.objects.filter(pk=self.alice_favourite.pk).exists())

        self.bob_account.user_profiles.add(self.alice_profile)
        for permission in (
            "users.view_favouriteasset",
            "users.change_favouriteasset",
            "users.delete_favouriteasset",
        ):
            remove_perm(permission, self.alice, self.bob_favourite)

        self.assertIn(self.bob_favourite, FavouriteAsset.objects.visible_to_user(self.alice))
        bob_url = f"/api/favourite-assets/{self.bob_favourite.uuid}/"
        self.assertEqual(self.client.get(bob_url).status_code, 200)
        self.assertEqual(self.client.delete(bob_url).status_code, 204)
        self.assertFalse(FavouriteAsset.objects.filter(pk=self.bob_favourite.pk).exists())

    def test_authenticated_routes_enforce_live_ownership(self):
        self.grant_alice_bob_permissions()
        self.remove_alice_view_permissions()
        self.client.force_authenticate(self.alice)

        list_cases = (
            ("/api/user-profiles/", self.alice_profile.uuid, self.bob_profile.uuid),
            ("/api/financial-profiles/", self.alice_financial.uuid, self.bob_financial.uuid),
            ("/api/favourite-assets/", self.alice_favourite.uuid, self.bob_favourite.uuid),
        )
        for url, own_uuid, foreign_uuid in list_cases:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                returned = {row["uuid"] for row in self.rows(response)}
                self.assertIn(str(own_uuid), returned)
                self.assertNotIn(str(foreign_uuid), returned)

        preferences_response = self.client.get("/api/user-preferences/")
        self.assertEqual(preferences_response.status_code, 200)
        self.assertEqual(preferences_response.json()["uuid"], str(self.alice_preferences.uuid))

        for url in (
            f"/api/user-profiles/{self.alice_profile.uuid}/",
            f"/api/financial-profiles/{self.alice_financial.uuid}/",
            f"/api/favourite-assets/{self.alice_favourite.uuid}/",
            f"/api/user-preferences/{self.alice_preferences.uuid}/",
        ):
            with self.subTest(own_url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

        foreign_cases = (
            ("get", f"/api/user-profiles/{self.bob_profile.uuid}/", None),
            ("patch", f"/api/user-profiles/{self.bob_profile.uuid}/", {"fullName": "Changed"}),
            ("get", f"/api/financial-profiles/{self.bob_financial.uuid}/", None),
            ("patch", f"/api/financial-profiles/{self.bob_financial.uuid}/", {"occupation": "Changed"}),
            ("get", f"/api/favourite-assets/{self.bob_favourite.uuid}/", None),
            ("delete", f"/api/favourite-assets/{self.bob_favourite.uuid}/", None),
            ("get", f"/api/user-preferences/{self.bob_preferences.uuid}/", None),
            ("patch", f"/api/user-preferences/{self.bob_preferences.uuid}/", {"theme": "light"}),
            ("delete", f"/api/user-preferences/{self.bob_preferences.uuid}/", None),
        )
        for method, url, payload in foreign_cases:
            with self.subTest(method=method, foreign_url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, 404)

        self.bob_profile.refresh_from_db()
        self.bob_financial.refresh_from_db()
        self.bob_preferences.refresh_from_db()
        self.assertEqual(self.bob_profile.full_name, "Bob")
        self.assertEqual(self.bob_financial.occupation, "Bob occupation")
        self.assertEqual(self.bob_preferences.theme, "dark")
        self.assertTrue(FavouriteAsset.objects.filter(pk=self.bob_favourite.pk).exists())

    def test_favourite_filters_cannot_expand_the_live_scope(self):
        self.client.force_authenticate(self.alice)

        response = self.client.get(
            "/api/favourite-assets/",
            {"user_account": str(self.bob_account.uuid)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows(response), [])

    def test_anonymous_fails_closed_and_privileged_users_keep_global_visibility(self):
        anonymous = AnonymousUser()
        managers = (
            UserProfile.objects,
            FinancialProfile.objects,
            UserPreferences.objects,
            FavouriteAsset.objects,
        )
        for manager in managers:
            with self.subTest(model=manager.model._meta.label, user="anonymous"):
                self.assertFalse(manager.visible_to_user(anonymous).exists())
                self.assertFalse(manager.visible_to_user(None).exists())

            for privileged_user in (self.staff, self.superuser):
                with self.subTest(model=manager.model._meta.label, user=privileged_user.email):
                    self.assertEqual(
                        set(manager.visible_to_user(privileged_user)),
                        set(manager.all()),
                    )
