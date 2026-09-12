from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from users.models import (
    DeviceToken,
    FavouriteAsset,
    FinancialProfile,
    InvestorClassification,
    Notification,
    NotificationPreferences,
    UserAccount,
    UserPreferences,
    UserProfile,
)

User = get_user_model()

CARRIED_BY_THE_POLICY = (
    ("UserProfile", UserProfile, "profile"),
    ("FavouriteAsset", FavouriteAsset, "favourite"),
    ("DeviceToken", DeviceToken, "device_token"),
    ("Notification", Notification, "notification"),
    ("InvestorClassification", InvestorClassification, "investor_classification"),
)

BACKFILLED_OWNER = (
    ("FinancialProfile", FinancialProfile, "financial_profile"),
    ("UserPreferences", UserPreferences, "preferences"),
    ("NotificationPreferences", NotificationPreferences, "notification_preferences"),
)


class UserOwnedModelsAreCarriedByThePolicyTest(RunsOnTheScopedConnection, TransactionTestCase):
    def setUp(self):
        super().setUp()
        with use_operator():
            self.mine = make_tenant("carried-mine")
            self.theirs = make_tenant("carried-theirs")

    def test_the_policy_alone_returns_the_principals_rows_and_no_others(self):
        self.the_principal_the_middleware_would_set(self.mine.user)
        for name, model, attribute in CARRIED_BY_THE_POLICY:
            with self.subTest(model=name):
                reachable = set(model.objects.for_the_current_principal().values_list("pk", flat=True))
                self.assertIn(getattr(self.mine, attribute).pk, reachable)
                self.assertNotIn(getattr(self.theirs, attribute).pk, reachable)
                self.assertEqual(reachable, set(model.objects.values_list("pk", flat=True)))

    def test_the_other_principal_reaches_its_own_rows_and_not_mine(self):
        self.the_principal_the_middleware_would_set(self.theirs.user)
        for name, model, attribute in CARRIED_BY_THE_POLICY:
            with self.subTest(model=name):
                reachable = set(model.objects.for_the_current_principal().values_list("pk", flat=True))
                self.assertIn(getattr(self.theirs, attribute).pk, reachable)
                self.assertNotIn(getattr(self.mine, attribute).pk, reachable)

    def test_no_principal_reaches_nothing(self):
        self.no_principal_is_set()
        for name, model, _ in CARRIED_BY_THE_POLICY:
            with self.subTest(model=name):
                self.assertEqual(model.objects.for_the_current_principal().count(), 0)

    def test_the_account_filter_is_retained_because_its_policy_admits_more(self):
        self.the_principal_the_middleware_would_set(self.mine.user)
        by_policy = set(UserAccount.objects.values_list("pk", flat=True))
        by_membership = set(
            UserAccount.objects.accounts_the_user_is_a_member_of(self.mine.user).values_list("pk", flat=True)
        )
        self.assertIn(self.theirs.account.pk, by_policy)
        self.assertEqual(by_membership, {self.mine.account.pk})

    def test_reassigning_a_profile_moves_its_rows_to_the_new_owner(self):
        with use_operator():
            replacement = User.objects.create_user(
                email="carried-replacement@tenants.example.test", password="pw-12345678"
            )
            profile = self.mine.profile
            profile.user = replacement
            profile.save(update_fields=["user"])

        self.the_principal_the_middleware_would_set(self.mine.user)
        self.assertNotIn(profile.pk, set(UserProfile.objects.for_the_current_principal().values_list("pk", flat=True)))

        self.the_principal_the_middleware_would_set(replacement)
        self.assertIn(profile.pk, set(UserProfile.objects.for_the_current_principal().values_list("pk", flat=True)))

    def test_a_backfilled_owner_column_goes_stale_so_its_queryset_is_retained(self):
        with use_operator():
            replacement = User.objects.create_user(email="stale-owner@tenants.example.test", password="pw-12345678")
            profile = self.mine.profile
            profile.user = replacement
            profile.save(update_fields=["user"])

        self.the_principal_the_middleware_would_set(self.mine.user)
        for name, model, attribute in BACKFILLED_OWNER:
            with self.subTest(model=name):
                row = getattr(self.mine, attribute).pk
                self.assertIn(row, set(model.objects.values_list("pk", flat=True)))
                self.assertFalse(model.objects.owned_through_the_live_profile(self.mine.user).filter(pk=row).exists())

    def test_account_membership_immediately_controls_favourite_access(self):
        self.the_principal_the_middleware_would_set(self.mine.user)
        reachable = FavouriteAsset.objects.for_the_current_principal()
        self.assertIn(self.mine.favourite.pk, set(reachable.values_list("pk", flat=True)))

        with use_operator():
            self.mine.account.user_profiles.remove(self.mine.profile)
        self.assertNotIn(
            self.mine.favourite.pk,
            set(FavouriteAsset.objects.for_the_current_principal().values_list("pk", flat=True)),
        )

        with use_operator():
            self.theirs.account.user_profiles.add(self.mine.profile)
        self.assertIn(
            self.theirs.favourite.pk,
            set(FavouriteAsset.objects.for_the_current_principal().values_list("pk", flat=True)),
        )

    def test_the_policy_carried_call_refuses_the_operator_connection(self):
        with use_operator():
            for name, model, _ in CARRIED_BY_THE_POLICY:
                with self.subTest(model=name):
                    with self.assertRaisesRegex(RuntimeError, "operator connection"):
                        model.objects.for_the_current_principal()


class UserOwnedRoutesUnderTheAppRoleTest(RunsOnTheScopedConnection, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        with use_operator():
            self.mine = make_tenant("routes-mine")
            self.theirs = make_tenant("routes-theirs")

    @staticmethod
    def rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_the_list_routes_return_only_the_principals_rows(self):
        self.signed_in_as(self.mine.user)
        listings = (
            ("/api/notifications/", self.mine.notification, self.theirs.notification),
            ("/api/favourite-assets/", self.mine.favourite, self.theirs.favourite),
            ("/api/device-tokens/", self.mine.device_token, self.theirs.device_token),
        )
        for url, own, foreign in listings:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content)
                uuids = {row["uuid"] for row in self.rows(response)}
                self.assertIn(str(own.uuid), uuids)
                self.assertNotIn(str(foreign.uuid), uuids)

    def test_a_filter_cannot_expand_the_scope(self):
        self.signed_in_as(self.mine.user)
        response = self.client.get("/api/favourite-assets/", {"user_account": str(self.theirs.account.uuid)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows(response), [])

    def test_a_foreign_row_is_a_404_and_survives_the_attempt(self):
        self.signed_in_as(self.mine.user)
        url = f"/api/favourite-assets/{self.theirs.favourite.uuid}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        with use_operator():
            self.assertTrue(FavouriteAsset.objects.filter(pk=self.theirs.favourite.pk).exists())

    def test_the_unread_count_ignores_another_principals_notification(self):
        with use_operator():
            Notification.objects.filter(pk=self.theirs.notification.pk).update(is_read=False)
            Notification.objects.filter(pk=self.mine.notification.pk).update(is_read=True)
        self.signed_in_as(self.mine.user)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").json(), {"unreadCount": 0})

    def test_unregistering_another_principals_device_is_refused(self):
        self.signed_in_as(self.mine.user)
        response = self.client.post(
            "/api/device-tokens/unregister/",
            {"pushToken": self.theirs.device_token.push_token},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        with use_operator():
            self.assertTrue(DeviceToken.objects.filter(pk=self.theirs.device_token.pk).exists())

    def test_the_classification_list_shows_only_the_principals_own(self):
        self.signed_in_as(self.mine.user)
        response = self.client.get("/api/investor-classifications/")
        self.assertEqual(response.status_code, 200, response.content)
        uuids = {row["uuid"] for row in self.rows(response)}
        self.assertIn(str(self.mine.investor_classification.uuid), uuids)
        self.assertNotIn(str(self.theirs.investor_classification.uuid), uuids)
        foreign = f"/api/investor-classifications/{self.theirs.investor_classification.uuid}/"
        self.assertEqual(self.client.get(foreign).status_code, 404)

    def test_a_taken_over_device_leaves_the_previous_owner_no_claim(self):
        token = self.mine.device_token.push_token
        self.signed_in_as(self.mine.user)
        self.assertIn(
            str(self.mine.device_token.uuid),
            {row["uuid"] for row in self.rows(self.client.get("/api/device-tokens/"))},
        )

        with use_operator():
            DeviceToken.objects.filter(pk=self.mine.device_token.pk).update(user=self.theirs.user)

        self.signed_in_as(self.mine.user)
        self.assertNotIn(
            token,
            {row["pushToken"] for row in self.rows(self.client.get("/api/device-tokens/"))},
        )
        self.signed_in_as(self.theirs.user)
        self.assertIn(
            token,
            {row["pushToken"] for row in self.rows(self.client.get("/api/device-tokens/"))},
        )
