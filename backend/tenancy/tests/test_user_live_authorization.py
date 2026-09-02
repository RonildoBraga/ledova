"""Application-level user-data isolation through live ownership relationships."""

from threading import Event, Thread
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase

from assets.models import Asset
from users.models import (
    DeviceToken,
    FavouriteAsset,
    FinancialProfile,
    Notification,
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
        self.superuser = User.objects.create_user(
            email="super-user@example.test",
            password="pw-12345678",
            is_superuser=True,
            is_staff=True,
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

    def test_live_scopes_follow_current_relationships(self):
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

        self.assertIn(self.bob_favourite, FavouriteAsset.objects.visible_to_user(self.alice))
        bob_url = f"/api/favourite-assets/{self.bob_favourite.uuid}/"
        self.assertEqual(self.client.get(bob_url).status_code, 200)
        self.assertEqual(self.client.delete(bob_url).status_code, 204)
        self.assertFalse(FavouriteAsset.objects.filter(pk=self.bob_favourite.pk).exists())

    def test_authenticated_routes_enforce_live_ownership(self):
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

    def test_privileged_customer_updates_are_self_scoped(self):
        for label, privileged_user in (
            ("staff", self.staff),
            ("superuser", self.superuser),
        ):
            own_profile = UserProfile.objects.create(
                user=privileged_user,
                full_name=f"{label.title()} owner",
            )
            own_financial = FinancialProfile.objects.create(
                user_profile=own_profile,
                occupation="Own occupation",
            )
            target_user = User.objects.create_user(
                email=f"{label}-target@example.test",
                password="pw-12345678",
            )
            target_profile = UserProfile.objects.create(
                user=target_user,
                full_name=f"{label.title()} target",
            )
            target_financial = FinancialProfile.objects.create(
                user_profile=target_profile,
                occupation="Original occupation",
            )
            self.client.force_authenticate(privileged_user)

            foreign_profile_response = self.client.patch(
                f"/api/user-profiles/{target_profile.uuid}/",
                {"fullName": f"Updated {label} target"},
                format="json",
            )
            foreign_financial_response = self.client.patch(
                f"/api/financial-profiles/{target_financial.uuid}/",
                {"occupation": f"Updated by {label}"},
                format="json",
            )
            own_profile_response = self.client.patch(
                f"/api/user-profiles/{own_profile.uuid}/",
                {"fullName": f"Updated {label} owner"},
                format="json",
            )
            own_financial_response = self.client.patch(
                f"/api/financial-profiles/{own_financial.uuid}/",
                {"occupation": f"Own update by {label}"},
                format="json",
            )

            with self.subTest(user=label):
                self.assertEqual(foreign_profile_response.status_code, 404)
                self.assertEqual(foreign_financial_response.status_code, 404)
                self.assertEqual(own_profile_response.status_code, 200)
                self.assertEqual(own_financial_response.status_code, 200)

                own_profile.refresh_from_db()
                own_financial.refresh_from_db()
                target_profile.refresh_from_db()
                target_financial.refresh_from_db()

                self.assertEqual(own_profile.user_id, privileged_user.pk)
                self.assertEqual(own_profile.full_name, f"Updated {label} owner")
                self.assertEqual(own_financial.user_profile_id, own_profile.pk)
                self.assertEqual(own_financial.occupation, f"Own update by {label}")
                self.assertEqual(target_profile.user_id, target_user.pk)
                self.assertEqual(target_profile.full_name, f"{label.title()} target")
                self.assertEqual(target_financial.user_profile_id, target_profile.pk)
                self.assertEqual(target_financial.occupation, "Original occupation")

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

    def test_favourite_filters_cannot_expand_the_live_scope(self):
        self.client.force_authenticate(self.alice)

        response = self.client.get(
            "/api/favourite-assets/",
            {"user_account": str(self.bob_account.uuid)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows(response), [])

    def test_anonymous_fails_closed_and_privileged_users_are_self_scoped(self):
        anonymous = AnonymousUser()
        managers = (
            UserProfile.objects,
            UserAccount.objects,
            FinancialProfile.objects,
            UserPreferences.objects,
            FavouriteAsset.objects,
            Notification.objects,
            NotificationPreferences.objects,
            DeviceToken.objects,
        )
        for manager in managers:
            with self.subTest(model=manager.model._meta.label, user="anonymous"):
                self.assertFalse(manager.visible_to_user(anonymous).exists())
                self.assertFalse(manager.visible_to_user(None).exists())

        for label, privileged_user in (("staff", self.staff), ("superuser", self.superuser)):
            profile = UserProfile.objects.create(user=privileged_user)
            account = UserAccount.objects.create(account_number=f"ACCOUNT-{label.upper()}")
            account.user_profiles.add(profile)
            financial = FinancialProfile.objects.create(user_profile=profile)
            preferences = UserPreferences.objects.create(user_profile=profile, selected_account=account)
            favourite = FavouriteAsset.objects.create(user_account=account, asset=self.asset)
            expected = (
                (UserProfile.objects, profile),
                (UserAccount.objects, account),
                (FinancialProfile.objects, financial),
                (UserPreferences.objects, preferences),
                (FavouriteAsset.objects, favourite),
            )

            for manager, own_object in expected:
                with self.subTest(model=manager.model._meta.label, user=privileged_user.email):
                    self.assertEqual(set(manager.visible_to_user(privileged_user)), {own_object})

            self.client.force_authenticate(privileged_user)
            for url, own_uuid in (
                ("/api/user-profiles/", profile.uuid),
                ("/api/user-accounts/", account.uuid),
                ("/api/financial-profiles/", financial.uuid),
                ("/api/favourite-assets/", favourite.uuid),
            ):
                with self.subTest(url=url, user=privileged_user.email):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        {row["uuid"] for row in self.rows(response)},
                        {str(own_uuid)},
                    )

            preferences_response = self.client.get("/api/user-preferences/")
            self.assertEqual(preferences_response.status_code, 200)
            self.assertEqual(preferences_response.json()["uuid"], str(preferences.uuid))


class OwnershipUpdateLockTest(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="lock-owner@example.test",
            password="pw-12345678",
        )
        self.profile_replacement_owner = User.objects.create_user(
            email="profile-lock-replacement@example.test",
            password="pw-12345678",
        )
        self.related_replacement_owner = User.objects.create_user(
            email="related-lock-replacement@example.test",
            password="pw-12345678",
        )
        self.profile = UserProfile.objects.create(
            user=self.owner,
            full_name="Original name",
        )
        self.related_replacement_profile = UserProfile.objects.create(
            user=self.related_replacement_owner,
            full_name="Related replacement",
        )
        self.financial_profile = FinancialProfile.objects.create(
            user_profile=self.profile,
            occupation="Original occupation",
        )
        self.account = UserAccount.objects.create(
            account_number="LOCK-ACCOUNT",
            director=self.profile,
            role="investor",
        )
        self.account.user_profiles.add(self.profile)

    def run_locked_patch(self, view_class, path, payload, concurrent_change):
        row_locked = Event()
        allow_patch = Event()
        change_started = Event()
        change_finished = Event()
        change_backend_pids = []
        errors = []
        response_statuses = []
        original_perform_update = view_class.perform_update

        def pause_after_lock(view, serializer):
            row_locked.set()
            if not allow_patch.wait(5):
                raise TimeoutError("Timed out waiting to continue the locked patch")
            return original_perform_update(view, serializer)

        def patch_object():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.owner)
                response = client.patch(path, payload, format="json")
                response_statuses.append(response.status_code)
            except BaseException as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        def change_object():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    change_backend_pids.append(cursor.fetchone()[0])
                change_started.set()
                concurrent_change()
            except BaseException as exc:
                errors.append(exc)
            finally:
                change_started.set()
                change_finished.set()
                close_old_connections()

        patch_thread = Thread(target=patch_object)
        change_thread = Thread(target=change_object)
        with patch.object(view_class, "perform_update", pause_after_lock):
            patch_thread.start()
            try:
                self.assertTrue(row_locked.wait(5))
                change_thread.start()
                self.assertTrue(change_started.wait(5))
                change_was_blocked = self.wait_until_database_change_is_blocked(
                    change_backend_pids,
                    change_finished,
                )
            finally:
                allow_patch.set()
                patch_thread.join(5)
                if change_thread.ident is not None:
                    change_thread.join(5)

        self.assertFalse(patch_thread.is_alive())
        self.assertFalse(change_thread.is_alive())
        if errors:
            raise errors[0]
        self.assertTrue(change_was_blocked)
        self.assertEqual(response_statuses, [200])
        self.assertTrue(change_finished.is_set())

    def wait_until_database_change_is_blocked(self, backend_pids, change_finished):
        deadline = monotonic() + 5
        while monotonic() < deadline:
            if backend_pids:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT cardinality(pg_blocking_pids(%s))",
                        [backend_pids[0]],
                    )
                    if cursor.fetchone()[0] > 0:
                        return True
            if change_finished.is_set():
                return False
            sleep(0.01)
        return False

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_owner_transfer_cannot_be_restored_by_stale_patch(self):
        self.run_locked_patch(
            UserProfileViewSet,
            f"/api/user-profiles/{self.profile.uuid}/",
            {"fullName": "Updated name"},
            lambda: UserProfile.objects.filter(pk=self.profile.pk).update(user=self.profile_replacement_owner),
        )

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.user_id, self.profile_replacement_owner.pk)
        self.assertEqual(self.profile.full_name, "Updated name")

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_financial_owner_transfer_cannot_be_restored_by_stale_patch(self):
        self.run_locked_patch(
            FinancialProfileViewSet,
            f"/api/financial-profiles/{self.financial_profile.uuid}/",
            {"occupation": "Updated occupation"},
            lambda: FinancialProfile.objects.filter(pk=self.financial_profile.pk).update(
                user_profile=self.related_replacement_profile
            ),
        )

        self.financial_profile.refresh_from_db()
        self.assertEqual(
            self.financial_profile.user_profile_id,
            self.related_replacement_profile.pk,
        )
        self.assertEqual(self.financial_profile.occupation, "Updated occupation")

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_profile_owner_transfer_waits_for_financial_patch(self):
        self.run_locked_patch(
            FinancialProfileViewSet,
            f"/api/financial-profiles/{self.financial_profile.uuid}/",
            {"occupation": "Updated after owner lock"},
            lambda: UserProfile.objects.filter(pk=self.profile.pk).update(user=self.profile_replacement_owner),
        )

        self.profile.refresh_from_db()
        self.financial_profile.refresh_from_db()
        self.assertEqual(self.profile.user_id, self.profile_replacement_owner.pk)
        self.assertEqual(
            self.financial_profile.occupation,
            "Updated after owner lock",
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_director_transfer_cannot_be_restored_by_stale_patch(self):
        self.run_locked_patch(
            UserAccountViewSet,
            f"/api/user-accounts/{self.account.uuid}/",
            {"role": "company"},
            lambda: UserAccount.objects.filter(pk=self.account.pk).update(director=self.related_replacement_profile),
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.director_id, self.related_replacement_profile.pk)
        self.assertEqual(self.account.role, "company")

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_membership_revocation_waits_for_authorized_patch(self):
        through_model = UserAccount.user_profiles.through
        self.run_locked_patch(
            UserAccountViewSet,
            f"/api/user-accounts/{self.account.uuid}/",
            {"role": "company"},
            lambda: through_model.objects.filter(
                useraccount=self.account,
                userprofile=self.profile,
            ).delete(),
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.role, "company")
        self.assertFalse(self.account.user_profiles.filter(pk=self.profile.pk).exists())
