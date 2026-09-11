import threading
from decimal import Decimal
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from eth_account import Account

from feature_flags.models import FeatureFlag
from shared.tests.tenants import make_tenant
from shared.utils.typed_data import signable_message
from tokens.exceptions import OrderCancellationException
from tokens.models import SigningChallenge, TransferOrder
from tokens.models.choices import TransferOrderStatus, TransferOrderType
from tokens.tests.order_action_fixtures import (
    cancel_for_order,
    cancel_message_for_order,
)

OWNER = Account.from_key("0x" + "3f" * 32)
JOIN_TIMEOUT = 30.0


@skipUnless(connection.vendor == "postgresql", "select_for_update is a no-op on SQLite")
class TwoCancelsOfOneOrderProduceOneCancellationTest(TransactionTestCase):

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("racer")
        self.tenant.wallet.address = OWNER.address
        self.tenant.wallet.save(update_fields=["address"])
        self.order = TransferOrder.objects.create(
            order_type=TransferOrderType.SELL,
            token=self.tenant.deployed_token,
            payment_asset=self.tenant.refs.stablecoin,
            wallet=self.tenant.wallet,
            owner_account=self.tenant.account,
            wallet_address=OWNER.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def a_signed_cancel(self):
        issued = cancel_message_for_order(self.tenant.user, self.order)
        signature = OWNER.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.to_0x_hex()
        return issued["digest"], signature

    def cancelling(self, signed):
        digest, signature = signed

        def work():
            return cancel_for_order(self.tenant.user, TransferOrder.objects.get(pk=self.order.pk), digest, signature)

        return work

    def _run(self, targets):
        outcomes = {}
        threads = [
            threading.Thread(target=self._wrap, args=(name, work, outcomes), name=name) for name, work in targets
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=JOIN_TIMEOUT)
        self.assertFalse(any(thread.is_alive() for thread in threads), outcomes)
        return outcomes

    @staticmethod
    def _wrap(name, work, outcomes):
        close_old_connections()
        try:
            outcomes[name] = work()
        except BaseException as exc:
            outcomes[name] = exc
        finally:
            connection.close()

    def test_only_one_of_two_concurrent_cancels_is_told_it_cancelled(self):
        first = self.a_signed_cancel()
        second = self.a_signed_cancel()

        outcomes = self._run([("first", self.cancelling(first)), ("second", self.cancelling(second))])

        refused = [name for name, outcome in outcomes.items() if isinstance(outcome, OrderCancellationException)]
        cancelled = [name for name, outcome in outcomes.items() if isinstance(outcome, TransferOrder)]

        self.assertEqual(len(cancelled), 1, outcomes)
        self.assertEqual(len(refused), 1, outcomes)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, TransferOrderStatus.CANCELLED)

    def test_both_signatures_are_spent_even_though_only_one_cancelled(self):
        first = self.a_signed_cancel()
        second = self.a_signed_cancel()

        self._run([("first", self.cancelling(first)), ("second", self.cancelling(second))])

        for digest, _ in (first, second):
            self.assertIsNotNone(SigningChallenge.objects.get(digest=digest).consumed_at, digest)


class ACancelFromAStaleReadDoesNotOverwriteAMatchTest(TransactionTestCase):

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("stale")
        self.tenant.wallet.address = OWNER.address
        self.tenant.wallet.save(update_fields=["address"])
        self.order = TransferOrder.objects.create(
            order_type=TransferOrderType.SELL,
            token=self.tenant.deployed_token,
            payment_asset=self.tenant.refs.stablecoin,
            wallet=self.tenant.wallet,
            owner_account=self.tenant.account,
            wallet_address=OWNER.address,
            quantity=10,
            price_per_share=Decimal("1.50"),
        )

    def a_signed_cancel(self):
        issued = cancel_message_for_order(self.tenant.user, self.order)
        signature = OWNER.sign_message(
            signable_message(issued["domain"], issued["types"], issued["message"])
        ).signature.to_0x_hex()
        return issued["digest"], signature

    def test_a_cancel_decided_on_a_read_taken_before_the_match_is_refused(self):
        digest, signature = self.a_signed_cancel()
        read_before_the_match = TransferOrder.objects.get(pk=self.order.pk)
        TransferOrder.objects.filter(pk=self.order.pk).update(status=TransferOrderStatus.MATCHED)

        with self.assertRaises(OrderCancellationException):
            cancel_for_order(self.tenant.user, read_before_the_match, digest, signature)

        self.assertEqual(TransferOrder.objects.get(pk=self.order.pk).status, TransferOrderStatus.MATCHED)

    def test_the_signature_that_lost_the_race_is_still_spent(self):
        digest, signature = self.a_signed_cancel()
        read_before_the_match = TransferOrder.objects.get(pk=self.order.pk)
        TransferOrder.objects.filter(pk=self.order.pk).update(status=TransferOrderStatus.MATCHED)

        with self.assertRaises(OrderCancellationException):
            cancel_for_order(self.tenant.user, read_before_the_match, digest, signature)

        self.assertIsNotNone(SigningChallenge.objects.get(digest=digest).consumed_at)
