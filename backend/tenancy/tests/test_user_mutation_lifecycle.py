from datetime import datetime
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from assets.models import Asset
from authentication.managers.user import V2EmailLookupResult, V2EmailLookupState
from authentication.models import UserToken
from authentication.security.v2_email import normalize_v2_email
from users.models import FavouriteAsset, FinancialProfile, UserAccount, UserProfile

User = get_user_model()


class UserMutationLifecycleTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="lifecycle-owner@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
        )
        self.member = User.objects.create_user(
            email="lifecycle-member@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
        )
        self.staff = User.objects.create_user(
            email="lifecycle-staff@example.test",
            password="pw-12345678",
            is_staff=True,
        )
        self.superuser = User.objects.create_user(
            email="lifecycle-superuser@example.test",
            password="pw-12345678",
            is_superuser=True,
        )
        self.owner_profile = UserProfile.objects.create(
            user=self.owner,
            full_name="Lifecycle Owner",
            phone_country_code="+61",
            phone_number="400000000",
            residential_address="Original address",
        )
        self.member_profile = UserProfile.objects.create(
            user=self.member,
            full_name="Lifecycle Member",
        )
        self.financial_profile = FinancialProfile.objects.create(
            user_profile=self.owner_profile,
            occupation="Original occupation",
        )
        self.account = UserAccount.objects.create(
            account_number="LIFECYCLE-ACCOUNT",
            director=self.owner_profile,
        )
        self.account.user_profiles.add(self.owner_profile, self.member_profile)
        self.asset = Asset.objects.create(
            symbol="LIFECYCLE",
            name="Lifecycle asset",
            asset_type="tokenized_security",
            is_active=True,
        )
        self.favourite = FavouriteAsset.objects.create(
            user_account=self.account,
            asset=self.asset,
        )

    def detail_urls(self):
        return (
            f"/api/user-profiles/{self.owner_profile.uuid}/",
            f"/api/financial-profiles/{self.financial_profile.uuid}/",
            f"/api/user-accounts/{self.account.uuid}/",
        )

    def test_generic_deletes_are_disabled_for_every_authenticated_role(self):
        for actor in (self.owner, self.member, self.staff, self.superuser):
            self.client.force_authenticate(actor)
            for url in self.detail_urls():
                with self.subTest(actor=actor.email, url=url):
                    self.assertEqual(self.client.delete(url).status_code, 405)

        self.assertTrue(UserProfile.objects.filter(pk=self.owner_profile.pk).exists())
        self.assertTrue(FinancialProfile.objects.filter(pk=self.financial_profile.pk).exists())
        self.assertTrue(UserAccount.objects.filter(pk=self.account.pk).exists())
        self.assertTrue(FavouriteAsset.objects.filter(pk=self.favourite.pk).exists())

        self.account.refresh_from_db()
        self.assertEqual(self.account.director_id, self.owner_profile.pk)
        self.assertEqual(
            set(self.account.user_profiles.values_list("pk", flat=True)),
            {self.owner_profile.pk, self.member_profile.pk},
        )

    def test_detail_options_do_not_advertise_delete(self):
        self.client.force_authenticate(self.owner)

        for url in self.detail_urls():
            with self.subTest(url=url):
                response = self.client.options(url)
                self.assertEqual(response.status_code, 200)
                allowed_methods = {method.strip() for method in response.headers["Allow"].split(",")}
                self.assertNotIn("DELETE", allowed_methods)
                self.assertTrue({"GET", "PUT", "PATCH", "HEAD", "OPTIONS"}.issubset(allowed_methods))

    def test_dedicated_account_deletion_keeps_shared_records_and_deactivates_only_requester(self):
        token = UserToken.objects.create(
            user=self.owner,
            access_token="test-access-token",
            refresh_token="test-refresh-token",
        )
        member_email = self.member.email
        self.client.force_authenticate(self.owner)

        with (
            patch("users.views.user_profile.datetime") as mocked_datetime,
            patch("users.views.user_profile.uuid4", return_value=UUID("12345678-1234-4123-8123-123456789abc")),
        ):
            mocked_datetime.now.return_value = datetime(2026, 9, 2, 4, 5, 6)
            response = self.client.post("/api/user-profiles/delete-account/")

        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.member.refresh_from_db()
        self.owner_profile.refresh_from_db()
        self.account.refresh_from_db()

        self.assertFalse(self.owner.is_active)
        self.assertFalse(self.owner.is_email_verified)
        expected_email = f"deleted_{self.owner.id}_20260902040506_12345678123441238123123456789abc@deleted.invalid"
        self.assertEqual(self.owner.email, expected_email)
        self.assertEqual(normalize_v2_email(self.owner.email), self.owner.email)
        self.assertNotEqual(self.owner.email, "lifecycle-owner@example.test")
        self.assertEqual(self.member.email, member_email)
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.owner_profile.full_name, "Deleted User")
        self.assertIsNone(self.owner_profile.phone_country_code)
        self.assertIsNone(self.owner_profile.phone_number)
        self.assertIsNone(self.owner_profile.residential_address)
        self.assertFalse(UserToken.objects.filter(pk=token.pk).exists())
        self.assertTrue(FinancialProfile.objects.filter(pk=self.financial_profile.pk).exists())
        self.assertTrue(UserAccount.objects.filter(pk=self.account.pk).exists())
        self.assertTrue(FavouriteAsset.objects.filter(pk=self.favourite.pk).exists())
        self.assertEqual(self.account.director_id, self.owner_profile.pk)
        self.assertEqual(
            set(self.account.user_profiles.values_list("pk", flat=True)),
            {self.owner_profile.pk, self.member_profile.pk},
        )

    def test_account_deletion_fails_before_mutation_when_tombstone_is_unavailable(self):
        original_email = self.owner.email
        token = UserToken.objects.create(
            user=self.owner,
            access_token="collision-access-token",
            refresh_token="collision-refresh-token",
        )
        tombstone = f"deleted_{self.owner.id}_20260902040506_12345678123441238123123456789abc@deleted.invalid"
        self.client.force_authenticate(self.owner)

        with (
            patch("users.views.user_profile.datetime") as mocked_datetime,
            patch("users.views.user_profile.uuid4", return_value=UUID("12345678-1234-4123-8123-123456789abc")),
            patch.object(
                type(User.objects),
                "resolve_v2_email",
                return_value=V2EmailLookupResult(V2EmailLookupState.AMBIGUOUS),
            ) as resolve,
        ):
            mocked_datetime.now.return_value = datetime(2026, 9, 2, 4, 5, 6)
            response = self.client.post("/api/user-profiles/delete-account/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": ["Account deletion could not be completed."]})
        resolve.assert_called_once_with(tombstone)
        self.owner.refresh_from_db()
        self.owner_profile.refresh_from_db()
        self.assertEqual(self.owner.email, original_email)
        self.assertTrue(self.owner.is_active)
        self.assertTrue(self.owner.is_email_verified)
        self.assertEqual(self.owner_profile.full_name, "Lifecycle Owner")
        self.assertTrue(UserToken.objects.filter(pk=token.pk).exists())
