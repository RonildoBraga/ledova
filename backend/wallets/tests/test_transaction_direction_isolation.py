from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from assets.models import Asset, AssetType
from users.models import UserAccount, UserProfile
from wallets.models import Transaction, Wallet

User = get_user_model()


class TransactionDirectionIsolationTest(APITestCase):
    def setUp(self):
        self.asset = Asset.objects.create(
            symbol="DIRECTION",
            name="Direction Test Asset",
            asset_type=AssetType.TOKENIZED_SECURITY.value,
            is_active=True,
            is_verified=True,
        )
        self.foreign_user, self.foreign_wallet = self._make_actor_wallet(
            "direction-foreign",
            "f",
        )
        self.actor_cases = (
            self._make_actor_case("direction-regular", "a"),
            self._make_actor_case("direction-staff", "b", is_staff=True),
            self._make_actor_case("direction-super", "c", is_superuser=True),
        )
        regular_wallet = self.actor_cases[0][1]
        self._make_transaction(
            self.foreign_wallet,
            "foreign-incoming",
            regular_wallet.address,
            self._case_variant(self.foreign_wallet.address),
        )
        self._make_transaction(
            self.foreign_wallet,
            "foreign-outgoing",
            self._case_variant(self.foreign_wallet.address),
            regular_wallet.address,
        )

    def _make_actor_wallet(self, label, address_character, **privileges):
        user = User.objects.create_user(
            email=f"{label}@example.test",
            password="pw-12345678",
            is_active=True,
            is_email_verified=True,
            **privileges,
        )
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create(account_number=label[:20])
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address="0x" + address_character * 40,
            chain="ethereum",
        )
        return user, wallet

    def _make_actor_case(self, label, address_character, **privileges):
        user, wallet = self._make_actor_wallet(label, address_character, **privileges)
        incoming = self._make_transaction(
            wallet,
            f"{label}-incoming",
            self.foreign_wallet.address,
            self._case_variant(wallet.address),
        )
        outgoing = self._make_transaction(
            wallet,
            f"{label}-outgoing",
            self._case_variant(wallet.address),
            self.foreign_wallet.address,
        )
        return user, wallet, incoming, outgoing

    def _make_transaction(self, wallet, tx_hash, from_address, to_address):
        return Transaction.objects.create(
            tx_hash=f"0x{tx_hash}",
            chain="ethereum",
            from_address=from_address,
            to_address=to_address,
            asset=self.asset,
            amount=Decimal("1"),
            wallet=wallet,
        )

    @staticmethod
    def _case_variant(address):
        return address.upper().replace("0X", "0x")

    @staticmethod
    def _response_rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body

    def test_queryset_direction_filters_bind_to_owned_wallet_for_every_role(self):
        for actor, wallet, incoming, outgoing in self.actor_cases:
            queryset = Transaction.objects.visible_to_user(actor)

            with self.subTest(actor=actor.email, direction="incoming"):
                self.assertEqual(
                    set(queryset.filter_by_direction("incoming", wallet.uuid)),
                    {incoming},
                )
                self.assertEqual(set(queryset.filter_by_direction("incoming")), {incoming})
                self.assertFalse(queryset.filter_by_direction("incoming", self.foreign_wallet.uuid).exists())

            with self.subTest(actor=actor.email, direction="outgoing"):
                self.assertEqual(
                    set(queryset.filter_by_direction("outgoing", wallet.uuid)),
                    {outgoing},
                )
                self.assertEqual(set(queryset.filter_by_direction("outgoing")), {outgoing})
                self.assertFalse(queryset.filter_by_direction("outgoing", self.foreign_wallet.uuid).exists())

    def test_api_direction_filters_bind_to_owned_wallet_for_every_role(self):
        for actor, wallet, incoming, outgoing in self.actor_cases:
            self.client.force_authenticate(actor)

            for direction, expected in (("incoming", incoming), ("outgoing", outgoing)):
                own_wallet_response = self.client.get(
                    "/api/transactions/",
                    {"wallet": str(wallet.uuid), "direction": direction},
                )
                no_wallet_response = self.client.get(
                    "/api/transactions/",
                    {"direction": direction},
                )
                foreign_wallet_response = self.client.get(
                    "/api/transactions/",
                    {"wallet": str(self.foreign_wallet.uuid), "direction": direction},
                )

                with self.subTest(actor=actor.email, direction=direction):
                    self.assertEqual(own_wallet_response.status_code, 200)
                    self.assertEqual(
                        {row["uuid"] for row in self._response_rows(own_wallet_response)},
                        {str(expected.uuid)},
                    )
                    self.assertEqual(no_wallet_response.status_code, 200)
                    self.assertEqual(
                        {row["uuid"] for row in self._response_rows(no_wallet_response)},
                        {str(expected.uuid)},
                    )
                    self.assertEqual(foreign_wallet_response.status_code, 200)
                    self.assertEqual(self._response_rows(foreign_wallet_response), [])
