from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from web3 import Web3

from companies.models import Company
from feature_flags.models import FeatureFlag
from tokens.models import (
    ShareToken,
    Stablecoin,
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


class TradingReadIsolationTest(APITestCase):
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
            payment_token=self.stablecoin,
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
        return SwapOrder.objects.create(
            sell_order=sell_order,
            buy_order=buy_order,
            share_token=self.share_token,
            payment_token=self.stablecoin,
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
        self.stablecoin = Stablecoin.objects.create(
            name="Test Dollar",
            symbol="TUSD",
            contract_address="0x" + "e" * 40,
            decimals=2,
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

    @patch("tokens.views.swap.AtomicSwapService")
    def test_pending_swaps_rejects_foreign_address_before_service_construction(self, service_class):
        self.client.force_authenticate(self.bob)
        response = self.client.get(
            "/api/v1/trading/swaps/",
            {"wallet_address": self.alice_wallet.address},
        )

        self.assertEqual(response.status_code, 404)
        service_class.assert_not_called()

    @patch("tokens.views.swap.AtomicSwapService")
    def test_pending_swaps_accepts_owned_case_variant_and_passes_wallet_ids(self, service_class):
        service_class.return_value.get_pending_swaps_for_wallet_ids.return_value = (
            SwapOrder.objects.pending_for_wallet_ids([self.bob_wallet.uuid])
        )
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            "/api/v1/trading/swaps/",
            {"wallet_address": self.bob_case_variant},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(self.swap.uuid))
        service_class.return_value.get_pending_swaps_for_wallet_ids.assert_called_once_with((self.bob_wallet.uuid,))

    @patch("tokens.views.swap.AtomicSwapService")
    def test_pending_swaps_are_paginated_and_newest_first(self, service_class):
        newer_swap = self._make_swap(self.alice_order, self.bob_order, "6")
        service_class.return_value.get_pending_swaps_for_wallet_ids.return_value = (
            SwapOrder.objects.pending_for_wallet_ids([self.bob_wallet.uuid])
        )
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

    @patch("tokens.views.trading_transfer.TransferService")
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

    @patch("tokens.views.trading_transfer.TransferService")
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

    @patch("whitelist.views.status.WhitelistService")
    def test_whitelist_status_allows_bounded_recipient_eligibility_check(self, service_class):
        service = service_class.return_value
        service.get_investor_info.return_value = {"whitelisted": True}
        service.can_receive.return_value = True
        service.chain_client.to_checksum_address.return_value = Web3.to_checksum_address(self.alice_wallet.address)
        self.client.force_authenticate(self.bob)
        response = self.client.get(f"/api/v1/trading/whitelist/{self.alice_wallet.address}/status/")

        self.assertEqual(response.status_code, 200)
        service.get_investor_info.assert_called_once_with(self.alice_wallet.address)
        service.can_receive.assert_called_once_with(self.alice_wallet.address)

    @patch("whitelist.views.status.WhitelistService")
    def test_whitelist_status_uses_canonical_owned_address(self, service_class):
        canonical = Web3.to_checksum_address(self.bob_wallet.address)
        service = service_class.return_value
        service.get_investor_info.return_value = {"whitelisted": True}
        service.can_receive.return_value = True
        service.chain_client.to_checksum_address.return_value = canonical
        self.client.force_authenticate(self.bob)

        response = self.client.get(f"/api/v1/trading/whitelist/{self.bob_case_variant}/status/")

        self.assertEqual(response.status_code, 200)
        service.get_investor_info.assert_called_once_with(self.bob_case_variant)
        service.can_receive.assert_called_once_with(self.bob_case_variant)

    @patch("tokens.views.trading_order.AtomicSwapService")
    def test_order_swap_role_is_derived_from_exact_transfer_order(self, service_class):
        service = service_class.return_value
        service.find_swap_order_by_transfer_order.return_value = self.swap
        service.get_typed_data.return_value = {}
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            f"/api/v1/trading/orders/{self.bob_order.uuid}/swap/",
            {"wallet_address": self.bob_case_variant},
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
                    {"wallet_address": self.bob_wallet.address},
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
                    {"wallet_address": self.bob_wallet.address},
                )
                self.assertEqual(response.status_code, 404)

        service_class.assert_not_called()

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
                "token": self.stablecoin.contract_address,
                "token_symbol": self.stablecoin.symbol,
                "required_amount": 1500,
                "current_allowance": 0,
                "has_sufficient_allowance": False,
            },
        }
        service.contract_address = "0x" + "8" * 40
        self.client.force_authenticate(self.bob)

        response = self.client.get(
            f"/api/v1/trading/orders/{self.bob_order.uuid}/swap/approval-status/",
            {"wallet_address": self.bob_case_variant},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_role"], "buyer")
        self.assertEqual(response.data["token_symbol"], self.stablecoin.symbol)
