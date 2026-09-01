"""The wallet owner FK must be scoped to the caller's own accounts.

Regression for the confirmed HIGH mass-assignment: the serializer previously
widened user_account to UserAccount.objects.all(), letting a tenant assign a
wallet into another tenant's account.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from users.models import UserAccount, UserProfile
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
                "custody_model": "non_custodial",
                "wallet_type": "software",
            },
            context=self._serializer_for(self.alice).context,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_account", serializer.errors)
