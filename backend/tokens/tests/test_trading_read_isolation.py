from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITransactionTestCase
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from companies.models import Company
from feature_flags.models import FeatureFlag
from shared.tests.schema import migrate_to, restore_every_migration
from shared.tests.settlement import (
    SYNTHETIC_SETTLEMENT_CONTRACT,
    save_swap_with_context,
)
from tokens.models import (
    ShareToken,
    SwapOrder,
    TransferOrder,
)
from tokens.models.choices import (
    ShareTokenStatus,
    ShareTokenType,
    SwapOrderStatus,
    TransferOrderStatus,
    TransferOrderType,
)
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


@override_settings(ATOMIC_SWAP_ADDRESS=SYNTHETIC_SETTLEMENT_CONTRACT)
class TradingReadIsolationTest(APITransactionTestCase):
    legacy_cases = {
        "test_malformed_address_snapshots_do_not_grant_swap_visibility",
        "test_order_swap_reads_reject_malformed_swap_snapshot_before_service",
        "test_a_malformed_newest_swap_is_not_replaced_by_an_older_valid_match",
    }

    def _make_tenant(self, email, address):
        user = User.objects.create_user(email=email, password="pw-12345678")
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account,
            address=address,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        return user, account, wallet

    def _make_order(self, wallet, order_type):
        return TransferOrder.objects.create(
            token=self.share_token,
            payment_asset=self.stablecoin,
            order_type=order_type,
            status=TransferOrderStatus.MATCHED,
            wallet=wallet,
            owner_account=wallet.user_account,
            wallet_address=wallet.address,
            quantity=10,
            filled_quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def _make_swap(self, sell_order, buy_order, suffix, status=SwapOrderStatus.CREATED):
        completed_at = timezone.now() if status == SwapOrderStatus.COMPLETED else None
        fields = dict(
            sell_order=sell_order,
            buy_order=buy_order,
            share_token=self.share_token,
            payment_asset=self.stablecoin,
            seller_address=sell_order.wallet_address,
            buyer_address=buy_order.wallet_address,
            share_amount=10,
            payment_amount=1500,
            nonce=int(suffix, 16),
            order_hash="0x" + suffix * 64,
            status=status,
            tx_hash="0x" + "f" * 64 if completed_at else "",
            completed_at=completed_at,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        if self._testMethodName not in self.legacy_cases:
            return save_swap_with_context(**fields)
        modules = getattr(settings, "MIGRATION_MODULES", {})
        if "tokens" in modules and modules["tokens"] is None:
            self.skipTest("Legacy malformed rows require actual pre-context migration setup")
        old_apps = migrate_to([("tokens", "0038_order_action_submissions")])
        self.addCleanup(restore_every_migration)
        for key in ("sell_order", "buy_order", "share_token", "payment_asset"):
            fields[key + "_id"] = fields.pop(key).pk
        fields["seller_wallet_id"] = sell_order.wallet_id
        fields["buyer_wallet_id"] = buy_order.wallet_id
        try:
            legacy = old_apps.get_model("tokens", "SwapOrder").objects.create(**fields)
        finally:
            restore_every_migration()
        return SwapOrder.objects.get(pk=legacy.pk)

    def swap_query(self, swap=None):
        swap = swap or self.swap
        if not swap.settlement_protocol_version:
            return {"wallet_address": self.bob_case_variant}
        return {
            "swap_uuid": str(swap.pk),
            "owner_account_uuid": str(self.bob_account.pk),
            "wallet_uuid": str(self.bob_wallet.pk),
            "settlement_digest": swap.settlement_digest,
        }

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.alice, self.alice_account, self.alice_wallet = self._make_tenant("alice@read.test", "0x" + "a" * 40)
        self.bob, self.bob_account, self.bob_wallet = self._make_tenant("bob@read.test", "0x" + "b" * 40)
        self.charlie, self.charlie_account, self.charlie_wallet = self._make_tenant(
            "charlie@read.test", "0x" + "c" * 40
        )

        self.company = Company.objects.create(
            owner=self.alice,
            name="Read Isolation Pty Ltd",
            company_type="private",
            acn="987654321",
            status="active",
        )
        self.share_token = ShareToken.objects.create(
            company=self.company,
            name="Read Isolation Ordinary",
            symbol="READ",
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + "d" * 40,
            deployment_tx_hash="0x" + "0" * 64,
        )
        self.stablecoin = Asset.objects.create(
            name="Test Dollar",
            symbol="TUSD",
            asset_type="stablecoin",
            decimals=2,
        )
        self.stablecoin_deployment = AssetChainDeployment.objects.create(
            asset=self.stablecoin, chain="base", contract_address="0x" + "e" * 40, decimals=2
        )
        self.alice_order = self._make_order(self.alice_wallet, TransferOrderType.SELL)
        self.bob_order = self._make_order(self.bob_wallet, TransferOrderType.BUY)
        self.swap = self._make_swap(self.alice_order, self.bob_order, "1")

    @property
    def bob_case_variant(self):
        return self.bob_wallet.address.upper().replace("0X", "0x")

    @patch("tokens.views.trading_wallet.ShareTokenService")
    def test_balances_rejects_foreign_address_before_service_construction(self, service_class):
        self.client.force_authenticate(self.bob)
        response = self.client.get(
            "/api/v1/trading/wallets/balances/",
            {"wallet_address": self.alice_wallet.address},
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.alice_wallet.address.lower(), str(response.data).lower())
        service_class.assert_not_called()

    @patch("tokens.views.trading_wallet.ShareTokenService")
    def test_balances_accepts_owned_case_variant_and_uses_canonical_address(self, service_class):
        service_class.return_value.get_wallet_token_balances.return_value = {"balances": []}
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            "/api/v1/trading/wallets/balances/",
            {"wallet_address": self.bob_case_variant},
        )

        self.assertEqual(response.status_code, 200)
        service_class.return_value.get_wallet_token_balances.assert_called_once_with(
            Web3.to_checksum_address(self.bob_wallet.address)
        )

    def test_pending_swaps_rejects_a_foreign_address(self):
        self.client.force_authenticate(self.bob)
        response = self.client.get(
            "/api/v1/trading/swaps/",
            {"wallet_address": self.alice_wallet.address},
        )

        self.assertEqual(response.status_code, 404)

    def test_pending_swaps_accepts_an_owned_case_variant(self):
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            "/api/v1/trading/swaps/",
            {"wallet_address": self.bob_case_variant},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.swap.uuid))

    def test_pending_swaps_are_paginated_and_newest_first(self):
        newer_swap = self._make_swap(self.alice_order, self.bob_order, "6")
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            "/api/v1/trading/swaps/",
            {"wallet_address": self.bob_wallet.address},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        self.assertEqual(
            [item["uuid"] for item in response.data["results"]],
            [str(newer_swap.uuid), str(self.swap.uuid)],
        )

    def test_same_address_on_different_wallet_row_does_not_grant_swap_visibility(self):
        duplicate_wallet = Wallet.objects.create(
            user_account=self.bob_account,
            address=self.alice_wallet.address,
            chain="base",
            verification_status="VERIFIED",
        )
        charlie_order = self._make_order(self.charlie_wallet, TransferOrderType.BUY)
        alice_charlie_swap = self._make_swap(self.alice_order, charlie_order, "2")

        visible = SwapOrder.objects.pending_for_wallet_ids([duplicate_wallet.uuid])

        self.assertNotIn(alice_charlie_swap.uuid, visible.values_list("uuid", flat=True))

    def test_malformed_address_snapshots_do_not_grant_swap_visibility(self):
        malformed_order = self._make_order(self.bob_wallet, TransferOrderType.BUY)
        malformed_order.wallet_address = self.alice_wallet.address
        malformed_order.save(update_fields=["wallet_address"])
        malformed_swap = self._make_swap(self.alice_order, malformed_order, "5")

        visible = SwapOrder.objects.pending_for_wallet_ids([self.bob_wallet.uuid])

        self.assertNotIn(malformed_swap.uuid, visible.values_list("uuid", flat=True))

        malformed_order.wallet_address = self.bob_wallet.address
        malformed_order.save(update_fields=["wallet_address"])
        malformed_swap.buyer_address = self.alice_wallet.address
        malformed_swap.save(update_fields=["buyer_address"])

        visible = SwapOrder.objects.pending_for_wallet_ids([self.bob_wallet.uuid])

        self.assertNotIn(malformed_swap.uuid, visible.values_list("uuid", flat=True))

    @patch("tokens.views.trading_transfer.TokenTransferService")
    def test_transfer_prepare_rejects_foreign_from_address_before_service_construction(self, service_class):
        self.client.force_authenticate(self.bob)
        response = self.client.post(
            "/api/v1/trading/transfers/prepare/",
            {
                "token": str(self.share_token.uuid),
                "from_address": self.alice_wallet.address,
                "to_address": self.bob_wallet.address,
                "amount": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        service_class.assert_not_called()

    @patch("tokens.views.trading_transfer.TokenTransferService")
    def test_transfer_prepare_uses_canonical_owned_from_address(self, service_class):
        service_class.return_value.prepare_transfer.return_value = {"to": self.share_token.contract_address}
        self.client.force_authenticate(self.bob)

        response = self.client.post(
            "/api/v1/trading/transfers/prepare/",
            {
                "token": str(self.share_token.uuid),
                "from_address": self.bob_case_variant,
                "to_address": self.alice_wallet.address,
                "amount": 1,
            },
            format="json",
        )

        canonical = Web3.to_checksum_address(self.bob_wallet.address)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["from_address"], canonical)
        service_class.return_value.prepare_transfer.assert_called_once_with(
            token=self.share_token,
            from_address=canonical,
            to_address=self.alice_wallet.address,
            amount=1,
        )

    @staticmethod
    def _whitelist_status_of(service, address):
        service.investor_status.return_value = {
            "address": address,
            "is_whitelisted": True,
            "can_receive": True,
            "status": "whitelisted",
        }

    @patch("whitelist.views.status.WhitelistService")
    def test_whitelist_status_allows_bounded_recipient_eligibility_check(self, service_class):
        service = service_class.return_value
        self._whitelist_status_of(service, Web3.to_checksum_address(self.alice_wallet.address))
        self.client.force_authenticate(self.bob)
        response = self.client.get(f"/api/v1/trading/whitelist/{self.alice_wallet.address}/status/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["isWhitelisted"])
        service.investor_status.assert_called_once_with(self.alice_wallet.address)

    @patch("whitelist.views.status.WhitelistService")
    def test_whitelist_status_uses_canonical_owned_address(self, service_class):
        service = service_class.return_value
        self._whitelist_status_of(service, Web3.to_checksum_address(self.bob_wallet.address))
        self.client.force_authenticate(self.bob)

        response = self.client.get(f"/api/v1/trading/whitelist/{self.bob_case_variant}/status/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["address"], Web3.to_checksum_address(self.bob_wallet.address))
        service.investor_status.assert_called_once_with(self.bob_case_variant)

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_order_swap_role_is_derived_from_exact_transfer_order(self, service_class):
        service = service_class.return_value
        service.find_swap_order_by_transfer_order.return_value = self.swap
        service.get_typed_data.return_value = {}
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            f"/api/v1/trading/orders/{self.bob_order.uuid}/swap/",
            self.swap_query(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_role"], "buyer")

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_order_swap_and_approval_reads_reject_other_owned_wallet_before_service(self, service_class):
        other_wallet = Wallet.objects.create(
            user_account=self.bob_account,
            address="0x" + "9" * 40,
            chain="base",
            verification_status="VERIFIED",
        )
        self.client.force_authenticate(self.bob)

        for path in ("swap/", "swap/approval-status/", "swap/approval-data/"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/v1/trading/orders/{self.bob_order.uuid}/{path}",
                    {"wallet_address": other_wallet.address},
                )
                self.assertEqual(response.status_code, 404)

        service_class.assert_not_called()

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_order_swap_reads_reject_malformed_order_snapshot_before_service(self, service_class):
        self.bob_order.wallet_address = self.alice_wallet.address
        self.bob_order.save(update_fields=["wallet_address"])
        self.client.force_authenticate(self.bob)

        for path in ("swap/", "swap/approval-status/", "swap/approval-data/"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/v1/trading/orders/{self.bob_order.uuid}/{path}",
                    self.swap_query(),
                )
                self.assertEqual(response.status_code, 404)

        service_class.assert_not_called()

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_order_swap_reads_reject_malformed_swap_snapshot_before_service(self, service_class):
        self.swap.buyer_address = self.alice_wallet.address
        self.swap.save(update_fields=["buyer_address"])
        self.client.force_authenticate(self.bob)

        for path in ("swap/", "swap/approval-status/", "swap/approval-data/"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/v1/trading/orders/{self.bob_order.uuid}/{path}",
                    self.swap_query(),
                )
                self.assertEqual(response.status_code, 404)

        service_class.assert_not_called()

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_a_malformed_newest_swap_is_not_replaced_by_an_older_valid_match(self, service_class):
        latest = self._make_swap(self.alice_order, self.bob_order, "7")
        latest.buyer_address = self.alice_wallet.address
        latest.save(update_fields=["buyer_address"])
        self.client.force_authenticate(self.bob)

        for path in ("swap/", "swap/approval-status/", "swap/approval-data/"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/v1/trading/orders/{self.bob_order.uuid}/{path}",
                    self.swap_query(),
                )
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["detail"], "Order not found.")
        service_class.assert_not_called()

        latest.buyer_address = self.bob_wallet.address
        latest.save(update_fields=["buyer_address"])
        service_class.return_value.get_typed_data.return_value = {}
        response = self.client.get(
            f"/api/v1/trading/orders/{self.bob_order.uuid}/swap/",
            self.swap_query(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["swap_order"]["uuid"], str(latest.uuid))
        self.assertEqual(response.data["user_role"], "buyer")

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_order_approval_status_uses_exact_order_role(self, service_class):
        service = service_class.return_value
        service.find_swap_order_by_transfer_order.return_value = self.swap
        service.check_swap_allowances.return_value = {
            "seller": {
                "token": self.share_token.contract_address,
                "token_symbol": self.share_token.symbol,
                "required_amount": 10,
                "current_allowance": 10,
                "has_sufficient_allowance": True,
            },
            "buyer": {
                "token": self.stablecoin_deployment.contract_address,
                "token_symbol": self.stablecoin.symbol,
                "required_amount": 1500,
                "current_allowance": 0,
                "has_sufficient_allowance": False,
            },
        }
        service.contract_address = "0x" + "8" * 40
        service.settlement_contract.return_value = service.contract_address
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            f"/api/v1/trading/orders/{self.bob_order.uuid}/swap/approval-status/",
            self.swap_query(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_role"], "buyer")
        self.assertEqual(response.data["token_symbol"], self.stablecoin.symbol)
