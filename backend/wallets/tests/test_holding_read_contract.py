from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from assets.models import Asset
from users.models import UserAccount, UserProfile
from wallets.models import Holding, Wallet

User = get_user_model()


class WalletHoldingReadContractTest(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="holding-alice@example.test",
            password="pw-12345678",
        )
        self.bob = User.objects.create_user(
            email="holding-bob@example.test",
            password="pw-12345678",
        )
        self.alice_profile = UserProfile.objects.create(user=self.alice)
        self.bob_profile = UserProfile.objects.create(user=self.bob)
        self.alice_account = UserAccount.objects.create(account_number="HOLDING-ALICE")
        self.bob_account = UserAccount.objects.create(account_number="HOLDING-BOB")
        self.alice_account.user_profiles.add(self.alice_profile)
        self.bob_account.user_profiles.add(self.bob_profile)
        self.alice_wallet = Wallet.objects.create(
            user_account=self.alice_account,
            address="0x" + "a" * 40,
            chain="ethereum",
        )
        self.bob_wallet = Wallet.objects.create(
            user_account=self.bob_account,
            address="0x" + "b" * 40,
            chain="ethereum",
        )
        self.active_verified_asset = Asset.objects.create(
            symbol="HOLDING-ACTIVE",
            name="Active verified holding asset",
            asset_type="tokenized_security",
            is_active=True,
            is_verified=True,
            current_price=Decimal("2"),
        )
        self.inactive_asset = Asset.objects.create(
            symbol="HOLDING-INACTIVE",
            name="Inactive holding asset",
            asset_type="tokenized_security",
            is_active=False,
            is_verified=True,
        )
        self.unverified_asset = Asset.objects.create(
            symbol="HOLDING-UNVERIFIED",
            name="Unverified holding asset",
            asset_type="tokenized_security",
            is_active=True,
            is_verified=False,
        )
        self.alice_holding = Holding.objects.create(
            wallet=self.alice_wallet,
            asset=self.active_verified_asset,
            quantity=Decimal("5"),
        )
        self.bob_holding = Holding.objects.create(
            wallet=self.bob_wallet,
            asset=self.active_verified_asset,
            quantity=Decimal("7"),
        )
        self.alice_inactive_holding = Holding.objects.create(
            wallet=self.alice_wallet,
            asset=self.inactive_asset,
            quantity=Decimal("11"),
        )
        self.alice_unverified_holding = Holding.objects.create(
            wallet=self.alice_wallet,
            asset=self.unverified_asset,
            quantity=Decimal("13"),
        )

    @staticmethod
    def holdings_url(wallet):
        return f"/api/wallets/{wallet.uuid}/holdings/?include_asset=true"

    def test_parent_wallet_membership_controls_holding_visibility(self):
        self.client.force_authenticate(self.alice)

        own_response = self.client.get(self.holdings_url(self.alice_wallet))
        foreign_response = self.client.get(self.holdings_url(self.bob_wallet))

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(
            {row["uuid"] for row in own_response.json()},
            {str(self.alice_holding.uuid)},
        )
        self.assertEqual(foreign_response.status_code, 404)

        self.alice_account.user_profiles.remove(self.alice_profile)

        revoked_response = self.client.get(self.holdings_url(self.alice_wallet))
        self.assertEqual(revoked_response.status_code, 404)
