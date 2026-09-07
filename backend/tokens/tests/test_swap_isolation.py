from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from assets.models import Asset
from companies.models import Company
from feature_flags.models import FeatureFlag
from tokens.models import ShareToken, SwapOrder, TransferOrder
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


class SwapQuerysetIsScopedToTheCallerTest(APITestCase):

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.owner, self.owner_wallet = self._tenant("swap-owner@example.test", "0x" + "1" * 40)
        self.stranger, self.stranger_wallet = self._tenant("swap-stranger@example.test", "0x" + "2" * 40)
        self.counterparty, self.counterparty_wallet = self._tenant("swap-counter@example.test", "0x" + "3" * 40)

        self.token, self.payment_asset = self._market()
        self.owner_swap = self._swap(self.owner_wallet, self.counterparty_wallet, "a")
        self.stranger_swap = self._swap(self.stranger_wallet, self.counterparty_wallet, "b")

    def _tenant(self, email, address):
        user = User.objects.create_user(email=email, password="pw-12345678")
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(
            user_account=account, address=address, chain="ethereum", verification_status="VERIFIED"
        )
        return user, wallet

    def _market(self):
        company = Company.objects.create(
            owner=self.owner, name="Swap Scope Pty Ltd", company_type="private", acn="123456789", status="active"
        )
        token = ShareToken.objects.create(
            company=company,
            name="Swap Scope Ordinary",
            symbol="SCOPE",
            token_type=ShareTokenType.ORDINARY,
            total_supply="1000000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + "d" * 40,
            deployment_tx_hash="0x" + "0" * 64,
        )
        asset = Asset.objects.create(name="Scope Dollar", symbol="SUSD", asset_type="stablecoin", decimals=2)
        return token, asset

    def _order(self, wallet, order_type):
        return TransferOrder.objects.create(
            token=self.token,
            payment_asset=self.payment_asset,
            order_type=order_type,
            status=TransferOrderStatus.MATCHED,
            wallet=wallet,
            owner_account=wallet.user_account,
            wallet_address=wallet.address,
            quantity=10,
            filled_quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def _swap(self, seller_wallet, buyer_wallet, suffix, status=SwapOrderStatus.CREATED):
        sell_order = self._order(seller_wallet, TransferOrderType.SELL)
        buy_order = self._order(buyer_wallet, TransferOrderType.BUY)
        return SwapOrder.objects.create(
            sell_order=sell_order,
            buy_order=buy_order,
            share_token=self.token,
            payment_asset=self.payment_asset,
            seller_address=sell_order.wallet_address,
            buyer_address=buy_order.wallet_address,
            share_amount=10,
            payment_amount=1500,
            nonce=int(suffix, 16),
            order_hash="0x" + suffix * 64,
            status=status,
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def _visible(self, user):
        return set(SwapOrder.objects.visible_to_user(user).values_list("uuid", flat=True))

    def test_the_caller_sees_a_swap_their_own_wallet_is_party_to(self):
        self.assertIn(self.owner_swap.uuid, self._visible(self.owner))

    def test_the_caller_never_sees_a_swap_between_other_wallets(self):
        self.assertNotIn(self.stranger_swap.uuid, self._visible(self.owner))

    def test_an_anonymous_caller_sees_nothing_even_though_swaps_exist(self):
        self.assertTrue(SwapOrder.objects.exists())
        self.assertEqual(self._visible(None), set())

    def test_an_unverified_wallet_stops_carrying_visibility(self):
        self.owner_wallet.verification_status = "PENDING"
        self.owner_wallet.save(update_fields=["verification_status"])

        self.assertNotIn(self.owner_swap.uuid, self._visible(self.owner))

    def test_the_listing_returns_only_the_callers_swap(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/v1/trading/swaps/", {"wallet_address": self.owner_wallet.address})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["uuid"] for row in response.data["results"]], [str(self.owner_swap.uuid)])

    def test_a_second_owned_wallet_does_not_widen_the_listing_for_the_first(self):
        second_wallet = Wallet.objects.create(
            user_account=self.owner_wallet.user_account,
            address="0x" + "4" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )
        second_swap = self._swap(second_wallet, self.counterparty_wallet, "c")
        self.client.force_authenticate(self.owner)

        visible = SwapOrder.objects.visible_to_user(self.owner).values_list("uuid", flat=True)
        self.assertIn(second_swap.uuid, visible)

        response = self.client.get("/api/v1/trading/swaps/", {"wallet_address": self.owner_wallet.address})

        self.assertEqual([row["uuid"] for row in response.data["results"]], [str(self.owner_swap.uuid)])

    def test_the_listing_refuses_a_wallet_the_caller_does_not_own(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/v1/trading/swaps/", {"wallet_address": self.stranger_wallet.address})

        self.assertEqual(response.status_code, 404)

    def test_the_listing_refuses_without_a_wallet_address(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/v1/trading/swaps/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"walletAddress": "This query parameter is required."})

    def test_a_completed_swap_is_not_listed_as_awaiting_signature(self):
        self.owner_swap.status = SwapOrderStatus.COMPLETED
        self.owner_swap.completed_at = timezone.now()
        self.owner_swap.save(update_fields=["status", "completed_at"])
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/v1/trading/swaps/", {"wallet_address": self.owner_wallet.address})

        self.assertEqual(response.data["results"], [])

    def test_a_swap_being_executed_is_not_listed_either(self):
        self.owner_swap.status = SwapOrderStatus.EXECUTING
        self.owner_swap.save(update_fields=["status"])
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/v1/trading/swaps/", {"wallet_address": self.owner_wallet.address})

        self.assertEqual(response.data["results"], [])
