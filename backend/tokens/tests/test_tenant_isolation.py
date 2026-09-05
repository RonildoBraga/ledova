"""Two-tenant cross-access tests for trading orders (deferred-hardening #1).

Regression net for the confirmed CRITICAL/HIGH IDORs on the trading order
endpoints: a tenant must never read another tenant's order — by list, by UUID
retrieve, or via a detail @action.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase
from web3 import Web3

from companies.models import Company
from feature_flags.models import FeatureFlag
from tokens.exceptions import InvalidRecipientAddressException
from tokens.models import ShareToken, TransferOrder
from tokens.models.choices import (
    ShareTokenStatus,
    ShareTokenType,
    TransferOrderStatus,
    TransferOrderType,
)
from tokens.serializers import TransferOrderCreateSerializer
from tokens.services import TransferService
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


class TenantOrderIsolationTest(APITestCase):
    def _make_tenant(self, email, address):
        user = User.objects.create_user(email=email, password="pw-12345678")
        user.is_active = True
        user.is_email_verified = True
        user.save()
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address=address,
            chain="ethereum",
            custody_model="non_custodial",
            wallet_type="software",
            verification_status="VERIFIED",
        )
        return user, account, wallet

    def _make_order(self, wallet, company_owner=None):
        company = Company.objects.create(
            owner=company_owner
            or User.objects.create_user(email=f"owner-{wallet.address}@ex.com", password="pw-12345678"),
            name="Acme Pty Ltd",
            company_type="private",
            acn=str(abs(hash(wallet.address)) % 10**9).zfill(9),
            status="active",
        )
        token = ShareToken.objects.create(
            company=company,
            name="Acme Ordinary",
            symbol="ACME",
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000000",
            status=ShareTokenStatus.DEPLOYED,
            deployment_tx_hash="0x" + "0" * 64,
        )
        return TransferOrder.objects.create(
            token=token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet=wallet,
            owner_account=wallet.user_account,
            wallet_address=wallet.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def setUp(self):
        FeatureFlag.objects.update_or_create(
            name="trading_enabled",
            defaults={"enabled": True},
        )
        self.alice, self.alice_account, self.alice_wallet = self._make_tenant("alice@ex.com", "0x" + "a" * 40)
        self.bob, self.bob_account, self.bob_wallet = self._make_tenant("bob@ex.com", "0x" + "b" * 40)
        self.alice_order = self._make_order(self.alice_wallet)
        self.bob_order = self._make_order(self.bob_wallet)

    def test_queryset_scoping_excludes_other_tenant(self):
        visible = TransferOrder.objects.visible_to_user(self.bob)
        uuids = set(visible.values_list("uuid", flat=True))
        self.assertIn(self.bob_order.uuid, uuids)
        self.assertNotIn(self.alice_order.uuid, uuids)

    def test_registering_another_tenants_address_does_not_grant_order_access(self):
        Wallet.objects.create(
            user_account=self.bob_account,
            address=self.alice_wallet.address,
            chain="ethereum",
            verification_status="VERIFIED",
        )

        visible = TransferOrder.objects.visible_to_user(self.bob)
        self.assertNotIn(self.alice_order.uuid, visible.values_list("uuid", flat=True))

    def test_mismatched_account_and_wallet_fail_closed_for_both_tenants(self):
        mismatched = TransferOrder.objects.create(
            token=self.alice_order.token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet=self.bob_wallet,
            owner_account=self.alice_account,
            wallet_address=self.bob_wallet.address,
            quantity=1,
            price_per_share=Decimal("1.00"),
        )

        self.assertNotIn(
            mismatched.uuid,
            TransferOrder.objects.visible_to_user(self.alice).values_list("uuid", flat=True),
        )
        self.assertNotIn(
            mismatched.uuid,
            TransferOrder.objects.visible_to_user(self.bob).values_list("uuid", flat=True),
        )

    def test_querysets_fail_closed_and_scope_privileged_users(self):
        for user in (None, AnonymousUser()):
            with self.subTest(user=user):
                self.assertFalse(TransferOrder.objects.visible_to_user(user).exists())

        mismatched = TransferOrder.objects.create(
            token=self.alice_order.token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet=self.bob_wallet,
            owner_account=self.alice_account,
            wallet_address=self.bob_wallet.address,
            quantity=1,
            price_per_share=Decimal("1.00"),
        )

        for index, privilege in enumerate(({"is_staff": True}, {"is_superuser": True, "is_staff": True}), start=3):
            actor, _, wallet = self._make_tenant(f"privileged-{index}@ex.com", "0x" + f"{index:x}" * 40)
            for field, value in privilege.items():
                setattr(actor, field, value)
            actor.save(update_fields=list(privilege))
            order = self._make_order(wallet, company_owner=actor)

            with self.subTest(actor=actor.email):
                self.assertEqual(set(TransferOrder.objects.visible_to_user(actor)), {order})
                self.assertNotIn(mismatched, TransferOrder.objects.visible_to_user(actor))


class TransferOrderOwnershipBindingTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create()
        self.account.user_profiles.add(self.profile)
        self.wallet = Wallet.objects.create(
            user_account=self.account,
            address="0x" + "a" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        self.pending_wallet = Wallet.objects.create(
            user_account=self.account,
            address="0x" + "b" * 40,
            chain="ethereum",
            verification_status="PENDING",
        )
        company = Company.objects.create(
            owner=self.user,
            name="Binding Test Pty Ltd",
            company_type="private",
            acn="123456789",
            status="active",
        )
        self.token = ShareToken.objects.create(
            company=company,
            name="Binding Test Ordinary",
            symbol="BIND",
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + "c" * 40,
            deployment_tx_hash="0x" + "0" * 64,
        )

    def _payload(self, wallet=None, address=None):
        wallet = wallet or self.wallet
        return {
            "token": str(self.token.uuid),
            "order_type": TransferOrderType.BUY,
            "wallet_uuid": str(wallet.uuid),
            "wallet_address": address or wallet.address,
            "quantity": 2,
            "price_per_share": "1.50",
        }

    def _serializer(self, payload):
        return TransferOrderCreateSerializer(
            data=payload,
            context={"request": SimpleNamespace(user=self.user)},
        )

    def test_exact_verified_wallet_and_account_are_bound(self):
        serializer = self._serializer(self._payload(address=Web3.to_checksum_address(self.wallet.address)))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["wallet"], self.wallet)
        self.assertEqual(serializer.validated_data["owner_account"], self.account)
        self.assertEqual(
            serializer.validated_data["wallet_address"],
            Web3.to_checksum_address(self.wallet.address),
        )

    def test_wallet_uuid_is_required(self):
        payload = self._payload()
        payload.pop("wallet_uuid")
        serializer = self._serializer(payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("wallet_uuid", serializer.errors)

    def test_pending_wallet_is_rejected(self):
        serializer = self._serializer(self._payload(wallet=self.pending_wallet))
        self.assertFalse(serializer.is_valid())
        self.assertIn("wallet_uuid", serializer.errors)

    def test_foreign_wallet_is_rejected(self):
        other_user = User.objects.create_user(email="other@example.test", password="pw-12345678")
        other_profile = UserProfile.objects.create(user=other_user)
        other_account = UserAccount.objects.create()
        other_account.user_profiles.add(other_profile)
        foreign_wallet = Wallet.objects.create(
            user_account=other_account,
            address="0x" + "d" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        serializer = self._serializer(self._payload(wallet=foreign_wallet))
        self.assertFalse(serializer.is_valid())
        self.assertIn("wallet_uuid", serializer.errors)

    def test_mismatched_address_is_rejected(self):
        serializer = self._serializer(self._payload(address="0x" + "e" * 40))
        self.assertFalse(serializer.is_valid())
        self.assertIn("wallet_address", serializer.errors)

    def test_one_user_can_select_the_exact_wallet_from_two_accounts(self):
        second_account = UserAccount.objects.create()
        second_account.user_profiles.add(self.profile)
        second_wallet = Wallet.objects.create(
            user_account=second_account,
            address=self.wallet.address.upper().replace("0X", "0x"),
            chain="base",
            verification_status="VERIFIED",
        )
        serializer = self._serializer(self._payload(wallet=second_wallet))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["wallet"], second_wallet)
        self.assertEqual(serializer.validated_data["owner_account"], second_account)

    def test_non_evm_wallet_is_rejected(self):
        bitcoin_wallet = Wallet.objects.create(
            user_account=self.account,
            address="0x" + "f" * 40,
            chain="bitcoin",
            verification_status="VERIFIED",
        )
        serializer = self._serializer(self._payload(wallet=bitcoin_wallet))
        self.assertFalse(serializer.is_valid())
        self.assertIn("wallet_uuid", serializer.errors)

    def test_matching_and_order_book_ignore_invalid_ownership_bindings(self):
        incoming = TransferOrder.objects.create(
            token=self.token,
            order_type=TransferOrderType.BUY,
            status=TransferOrderStatus.OPEN,
            wallet=self.wallet,
            owner_account=self.account,
            wallet_address=self.wallet.address,
            quantity=10,
            price_per_share=Decimal("2.00"),
        )
        TransferOrder.objects.create(
            token=self.token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet=self.pending_wallet,
            owner_account=self.account,
            wallet_address=self.pending_wallet.address,
            quantity=10,
            price_per_share=Decimal("1.10"),
        )

        counter_user = User.objects.create_user(email="counter@example.test", password="pw-12345678")
        counter_profile = UserProfile.objects.create(user=counter_user)
        counter_account = UserAccount.objects.create()
        counter_account.user_profiles.add(counter_profile)
        counter_wallet = Wallet.objects.create(
            user_account=counter_account,
            address="0x" + "c" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        valid_candidate = TransferOrder.objects.create(
            token=self.token,
            order_type=TransferOrderType.SELL,
            status=TransferOrderStatus.OPEN,
            wallet=counter_wallet,
            owner_account=counter_account,
            wallet_address=counter_wallet.address,
            quantity=10,
            price_per_share=Decimal("1.20"),
        )

        mismatched = TransferOrder.objects.filter(price_per_share=Decimal("1.10")).get()
        mismatched.owner_account = counter_account
        mismatched.save(update_fields=["owner_account"])

        service = TransferService.__new__(TransferService)
        match = service.find_matching_order(incoming)
        sell_levels = list(TransferOrder.objects.order_book_levels(self.token, TransferOrderType.SELL))

        self.assertIsNotNone(match)
        self.assertEqual(match[0], valid_candidate)
        self.assertEqual(len(sell_levels), 1)
        self.assertEqual(sell_levels[0]["price_per_share"], Decimal("1.20"))
        self.assertEqual(TransferOrder.objects.best_ask(self.token), valid_candidate)

    @patch("tokens.events.publish_trading_event")
    @patch("tokens.services.transfer_service.WhitelistService")
    @patch("tokens.services.transfer_service.get_base_chain_client")
    def test_service_persists_wallet_and_account_snapshot(self, get_client, whitelist_service, _publish_trading_event):
        chain_client = Mock()
        chain_client.is_valid_address.return_value = True
        chain_client.to_checksum_address.side_effect = Web3.to_checksum_address
        get_client.return_value = chain_client
        whitelist_service.return_value.is_whitelisted.return_value = True

        service = TransferService()
        service.find_matching_order = Mock(return_value=None)
        order, match = service.create_order_and_match(
            token=self.token,
            order_type=TransferOrderType.BUY,
            actor=self.user,
            wallet=self.wallet,
            owner_account=self.account,
            wallet_address=self.wallet.address,
            quantity=2,
            price_per_share=Decimal("1.50"),
        )

        self.assertIsNone(match)
        self.assertEqual(order.wallet, self.wallet)
        self.assertEqual(order.owner_account, self.account)
        self.assertEqual(order.wallet_address, Web3.to_checksum_address(self.wallet.address))

    @patch("tokens.services.transfer_service.WhitelistService")
    @patch("tokens.services.transfer_service.get_base_chain_client")
    def test_service_rejects_wallet_changed_after_validation(self, get_client, whitelist_service):
        chain_client = Mock()
        chain_client.is_valid_address.return_value = True
        chain_client.to_checksum_address.side_effect = Web3.to_checksum_address
        get_client.return_value = chain_client
        whitelist_service.return_value.is_whitelisted.return_value = True

        Wallet.objects.filter(pk=self.wallet.pk).update(verification_status="PENDING")

        with self.assertRaises(InvalidRecipientAddressException):
            TransferService().create_order_and_match(
                token=self.token,
                order_type=TransferOrderType.BUY,
                actor=self.user,
                wallet=self.wallet,
                owner_account=self.account,
                wallet_address=self.wallet.address,
                quantity=2,
                price_per_share=Decimal("1.50"),
            )

        Wallet.objects.filter(pk=self.wallet.pk).update(verification_status="VERIFIED")
        replacement_account = UserAccount.objects.create()
        replacement_account.user_profiles.add(self.profile)
        Wallet.objects.filter(pk=self.wallet.pk).update(user_account=replacement_account)

        with self.assertRaises(InvalidRecipientAddressException):
            TransferService().create_order_and_match(
                token=self.token,
                order_type=TransferOrderType.BUY,
                actor=self.user,
                wallet=self.wallet,
                owner_account=self.account,
                wallet_address=self.wallet.address,
                quantity=2,
                price_per_share=Decimal("1.50"),
            )

    @patch("tokens.services.transfer_service.WhitelistService")
    @patch("tokens.services.transfer_service.get_base_chain_client")
    def test_service_rechecks_actor_membership_after_validation(self, get_client, whitelist_service):
        serializer = self._serializer(self._payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)

        self.account.user_profiles.remove(self.profile)

        with self.assertRaises(InvalidRecipientAddressException):
            TransferService().create_order_and_match(
                token=self.token,
                order_type=TransferOrderType.BUY,
                actor=self.user,
                wallet=serializer.validated_data["wallet"],
                owner_account=serializer.validated_data["owner_account"],
                wallet_address=serializer.validated_data["wallet_address"],
                quantity=2,
                price_per_share=Decimal("1.50"),
            )

        self.assertFalse(TransferOrder.objects.exists())
