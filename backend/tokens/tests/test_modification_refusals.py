from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connections
from django.utils import timezone
from eth_account import Account
from rest_framework.test import APITransactionTestCase

from feature_flags.models import FeatureFlag
from shared.db import APP_ALIAS, acting_for, atomic, current_alias, use_operator
from shared.db.aliases import configured
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.models import OrderModificationLog, SigningChallenge, TransferOrder
from tokens.models.choices import TransferOrderStatus, TransferOrderType
from tokens.services import OrderModificationService
from tokens.services.signing_challenge import spend
from wallets.models import Wallet

OWNER = Account.from_key("0x" + "64" * 32)
STRANGER = Account.from_key("0x" + "65" * 32)


class ModificationChecks:
    def setUp(self):
        super().setUp()
        with use_operator():
            FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
            self.tenant = make_tenant("modification-refusal")
            wallet = Wallet.objects.create(
                user_account=self.tenant.account, address=OWNER.address, chain="base", verification_status="VERIFIED"
            )
            self.order = TransferOrder.objects.create(
                token=self.tenant.deployed_token,
                payment_asset=self.tenant.refs.stablecoin,
                wallet=wallet,
                owner_account=self.tenant.account,
                wallet_address=OWNER.address,
                order_type=TransferOrderType.BUY,
                quantity=10,
                min_quantity=0,
                price_per_share=Decimal("1.50"),
            )
        self.client.force_authenticate(self.tenant.user)
        self.balance = 200
        self.balance_error = None
        self.before_balance_return = None
        self.balance_observations = []
        provider = patch(
            "tokens.services.order_modification_service.ShareTokenService",
            return_value=SimpleNamespace(get_token_balance=self.read_balance),
        )
        self.addCleanup(provider.stop)
        provider.start()
        events = patch("tokens.events.publish_trading_event")
        self.addCleanup(events.stop)
        self.events = events.start()

    def read_balance(self, contract, wallet_address):
        alias = current_alias()
        self.balance_observations.append((alias, connections[alias].in_atomic_block))
        if self.balance_error:
            raise self.balance_error
        if self.before_balance_return:
            self.before_balance_return()
        return self.balance

    def change_order(self, **values):
        with use_operator(), atomic():
            connection = connections[current_alias()]
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '100ms'")
            TransferOrder.objects.filter(pk=self.order.pk).update(**values)
            self.order.refresh_from_db()

    def issue(self, quantity=12, minimum=0, price="2.00", signer=OWNER):
        with acting_for(self.tenant.user.pk):
            issued = OrderModificationService().generate_modification_message(
                self.order, new_quantity=quantity, new_min_quantity=minimum, new_price=Decimal(price)
            )
        signature = signer.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.to_0x_hex()
        self.balance_observations.clear()
        return {"digest": issued["digest"], "signature": signature}

    def apply(self, signed):
        return self.client.post(f"/api/v1/trading/orders/{self.order.uuid}/modify/", signed, format="json")

    def assert_spent_without_modification(self, signed):
        with use_operator():
            self.assertTrue(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
            self.order.refresh_from_db()
            self.assertEqual(self.order.quantity, 10)
            self.assertEqual(self.order.modification_count, 0)
            self.assertFalse(OrderModificationLog.objects.filter(order=self.order).exists())
        self.events.assert_not_called()

    def test_a_status_refusal_spends_the_signature_even_if_the_order_reopens(self):
        signed = self.issue()
        self.change_order(status=TransferOrderStatus.CANCELLED)
        response = self.apply(signed)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("Cancelled", response.json()["detail"])
        self.assert_spent_without_modification(signed)
        self.change_order(status=TransferOrderStatus.OPEN)
        replay = self.apply(signed)
        self.assertEqual(replay.status_code, 409, replay.content)
        self.assertIn("already", replay.json()["detail"].lower())

    def test_fills_that_make_the_signed_minimum_invalid_still_leave_the_signature_spent(self):
        signed = self.issue(quantity=12, minimum=8)
        self.change_order(filled_quantity=9, status=TransferOrderStatus.PARTIALLY_FILLED)
        response = self.apply(signed)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("Min quantity", response.json()["detail"])
        self.assert_spent_without_modification(signed)

    def test_a_sell_increase_reads_the_chain_before_any_transaction_or_order_lock(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20)
        response = self.apply(signed)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.balance_observations, [(configured(APP_ALIAS), False)])
        self.events.assert_called_once_with("order_modified", str(self.order.token_id))

    def test_insufficient_advisory_balance_refuses_but_commits_the_spend(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20)
        self.balance = 0
        response = self.apply(signed)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("Insufficient token balance", response.json()["detail"])
        self.assert_spent_without_modification(signed)
        self.assertEqual(self.balance_observations, [(configured(APP_ALIAS), False)])

    def test_an_invalid_signature_is_refused_before_a_chain_read(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20, signer=STRANGER)
        response = self.apply(signed)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.balance_observations, [])
        with use_operator():
            self.assertFalse(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
        self.events.assert_not_called()

    def test_a_provider_failure_before_the_lock_leaves_the_signature_retryable(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20)
        self.balance_error = ConnectionError("synthetic provider unavailable")
        response = self.apply(signed)
        self.assertEqual(response.status_code, 400, response.content)
        with use_operator():
            self.assertFalse(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
        self.balance_error = None
        retry = self.apply(signed)
        self.assertEqual(retry.status_code, 200, retry.content)

    def test_a_state_change_during_the_chain_read_is_checked_again_under_the_lock(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20)
        self.before_balance_return = lambda: self.change_order(status=TransferOrderStatus.CANCELLED)
        response = self.apply(signed)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("Cancelled", response.json()["detail"])
        self.assert_spent_without_modification(signed)
        self.assertEqual(self.order.status, TransferOrderStatus.CANCELLED)

    def test_a_price_only_sell_change_needs_no_chain_read(self):
        self.change_order(order_type=TransferOrderType.SELL)
        self.balance_error = ConnectionError("synthetic provider unavailable")
        signed = self.issue(quantity=10)
        response = self.apply(signed)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.balance_observations, [])

    def test_expiry_during_the_chain_read_is_checked_again_before_modifying(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20)

        def expire():
            with use_operator():
                SigningChallenge.objects.filter(digest=signed["digest"]).update(expires_at=timezone.now())

        self.before_balance_return = expire
        response = self.apply(signed)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("expired", response.json()["detail"].lower())
        with use_operator():
            self.assertFalse(SigningChallenge.objects.get(digest=signed["digest"]).is_consumed)
            self.order.refresh_from_db()
            self.assertEqual(self.order.quantity, 10)
        self.events.assert_not_called()

    def test_a_signature_spent_during_the_chain_read_is_not_applied_again(self):
        self.change_order(order_type=TransferOrderType.SELL)
        signed = self.issue(quantity=20)

        def consume_elsewhere():
            with use_operator(), atomic():
                challenge = SigningChallenge.objects.select_for_update().get(digest=signed["digest"])
                spend(challenge, signed["signature"])

        self.before_balance_return = consume_elsewhere
        response = self.apply(signed)
        self.assertEqual(response.status_code, 409, response.content)
        self.assert_spent_without_modification(signed)


class ModificationRefusalTest(ModificationChecks, APITransactionTestCase):
    pass


class ScopedModificationRefusalTest(RunsOnTheScopedConnection, ModificationChecks, APITransactionTestCase):
    pass
