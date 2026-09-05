"""The wallet owner FK must be scoped to the caller's own accounts.

Regression for the confirmed HIGH mass-assignment: the serializer previously
widened user_account to UserAccount.objects.all(), letting a tenant assign a
wallet into another tenant's account.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from users.models import UserAccount, UserProfile
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from wallets.serializers.wallet import WalletSerializer

User = get_user_model()


class WalletOwnerScopingTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice@ex.com", password="pw-12345678")
        self.bob = User.objects.create_user(email="bob@ex.com", password="pw-12345678")
        self.alice_account = UserAccount.objects.create()
        self.alice_account.user_profiles.add(UserProfile.objects.create(user=self.alice))
        self.bob_account = UserAccount.objects.create()
        self.bob_account.user_profiles.add(UserProfile.objects.create(user=self.bob))

    def _serializer_for(self, user):
        request = APIRequestFactory().post("/api/wallets/")
        request.user = user
        return WalletSerializer(context={"request": request})

    def test_owner_field_scoped_to_caller_accounts(self):
        qs = self._serializer_for(self.alice).fields["user_account"].queryset
        ids = set(qs.values_list("uuid", flat=True))
        self.assertIn(self.alice_account.uuid, ids)
        self.assertNotIn(self.bob_account.uuid, ids)

    def test_assigning_other_tenant_account_fails_validation(self):
        serializer = WalletSerializer(
            data={
                "user_account": str(self.bob_account.uuid),
                "address": "0x" + "c" * 40,
                "chain": "ethereum",
                "wallet_type": "software",
            },
            context=self._serializer_for(self.alice).context,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_account", serializer.errors)

    def test_verified_wallet_identity_fields_are_immutable(self):
        wallet = Wallet.objects.create(
            user_account=self.alice_account,
            address="0x" + "a" * 40,
            chain="ethereum",
            verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
        )
        second_alice_account = UserAccount.objects.create()
        second_alice_account.user_profiles.add(self.alice_account.user_profiles.get())

        cases = (
            ({"address": "0x" + "d" * 40}, "address"),
            ({"chain": "base"}, "chain"),
            ({"user_account": str(second_alice_account.uuid)}, "user_account"),
        )
        for payload, field in cases:
            with self.subTest(field=field):
                serializer = WalletSerializer(
                    wallet,
                    data=payload,
                    partial=True,
                    context=self._serializer_for(self.alice).context,
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn(field, serializer.errors)


class LiveMembershipScopingTest(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice-membership@ex.com", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.alice)
        self.account = UserAccount.objects.create()
        self.account.user_profiles.add(self.profile)
        self.wallet = Wallet.objects.create(
            user_account=self.account,
            address="0x" + "a" * 40,
            chain="ethereum",
        )

    def _serializer_for(self, user):
        request = APIRequestFactory().post("/api/wallets/")
        request.user = user
        return WalletSerializer(context={"request": request})

    def test_membership_removal_revokes_account_and_wallet_visibility(self):
        self.account.user_profiles.remove(self.profile)

        self.assertNotIn(
            self.account.uuid,
            UserAccount.objects.visible_to_user(self.alice).values_list("uuid", flat=True),
        )
        self.assertNotIn(
            self.wallet.uuid,
            Wallet.objects.visible_to_user(self.alice).values_list("uuid", flat=True),
        )

    def test_membership_addition_reveals_preexisting_account_wallet(self):
        preexisting_account = UserAccount.objects.create()
        preexisting_wallet = Wallet.objects.create(
            user_account=preexisting_account,
            address="0x" + "b" * 40,
            chain="ethereum",
        )

        preexisting_account.user_profiles.add(self.profile)

        self.assertIn(
            preexisting_account.uuid,
            UserAccount.objects.visible_to_user(self.alice).values_list("uuid", flat=True),
        )
        self.assertIn(
            preexisting_wallet.uuid,
            Wallet.objects.visible_to_user(self.alice).values_list("uuid", flat=True),
        )

    def test_wallet_serializer_owner_field_excludes_account_after_membership_removal(self):
        self.account.user_profiles.remove(self.profile)

        queryset = self._serializer_for(self.alice).fields["user_account"].queryset

        self.assertNotIn(self.account.uuid, queryset.values_list("uuid", flat=True))

    def test_staff_and_superuser_account_scope_follows_membership(self):
        staff = User.objects.create_user(email="staff-membership@ex.com", password="pw-12345678", is_staff=True)
        superuser = User.objects.create_user(
            email="superuser-membership@ex.com",
            password="pw-12345678",
            is_superuser=True,
            is_staff=True,
        )

        for privileged_user in (staff, superuser):
            profile = UserProfile.objects.create(user=privileged_user)
            own_account = UserAccount.objects.create()
            own_account.user_profiles.add(profile)

            with self.subTest(user=privileged_user.email):
                self.assertNotIn(
                    self.account.uuid,
                    UserAccount.objects.visible_to_user(privileged_user).values_list("uuid", flat=True),
                )
                self.assertIn(
                    own_account.uuid,
                    UserAccount.objects.visible_to_user(privileged_user).values_list("uuid", flat=True),
                )
                serializer = self._serializer_for(privileged_user)
                account_ids = set(serializer.fields["user_account"].queryset.values_list("uuid", flat=True))
                self.assertEqual(account_ids, {own_account.uuid})
