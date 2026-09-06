import threading
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APITransactionTestCase

from assets.models import Asset
from offerings.models import (
    Offering,
    OfferingExemption,
    OfferingStatus,
    SettlementRail,
    Subscription,
    SubscriptionStatus,
)
from offerings.services.subscription import (
    accept,
    allot,
    allot_batch,
    confirm_payment,
    create_draft,
    issue_instruction,
    submit,
)
from offerings.tasks import allot_subscription_task, reconcile_subscriptions
from offerings.tests.factories import (
    configure_operator,
    eligible_subscriber,
    forget_fixture_subscriptions,
)
from tokens.models import (
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
)
from tokens.services.share_token_service import SHARE_ASSET_CHAIN
from tokens.tests.test_chain_integration import (
    CAP,
    CHAIN_SETTINGS,
    ChainTestMixin,
    chain_available,
)
from wallets.models import Holding, Wallet
from whitelist.services import WhitelistService

DEFER = "offerings.tasks.subscription.allot_subscription_task.defer"
PRICE = Decimal("2.50")


class AllotmentChainMixin(ChainTestMixin):
    def setUp(self):
        super().setUp()
        self.defer = patch(DEFER).start()
        self.addCleanup(patch.stopall)
        forget_fixture_subscriptions()
        configure_operator()
        eligible_subscriber(self.tenant)
        self.wallet = Wallet.objects.get(address=self.investor)

    def _offering(self):
        return Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=PRICE,
            minimum_shares=1,
            target_shares=10,
            cap_shares=CAP,
            opens_at=timezone.now() - timedelta(days=1),
            status=OfferingStatus.APPROVED,
        )

    def _paid(self, offering, quantity):
        subscription = create_draft(offering, self.tenant.account, self.wallet, quantity, self.tenant.user)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        confirm_payment(
            subscription,
            confirmed_by=self.staff,
            amount_received=Decimal(quantity) * PRICE,
            received_on=timezone.now().date(),
            reference_seen=subscription.reference,
        )
        subscription.refresh_from_db()
        return subscription

    def _run_task(self, subscription):
        return allot_subscription_task(str(subscription.uuid), executed_by=self.staff.pk)


@chain_available
@override_settings(**CHAIN_SETTINGS)
class SubscriptionAllotmentChainTest(AllotmentChainMixin, APITestCase):
    def test_a_paid_subscription_mints_once_and_the_shares_reach_the_investors_portfolio(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        offering = self._offering()
        subscription = self._paid(offering, quantity=40)

        request = allot(subscription, self.staff, notes="Allotted from the operator console")
        self.assertEqual(request.status, RequestStatus.APPROVED)
        self.assertEqual(self.defer.call_count, 1)
        self.assertEqual(self._contract().functions.totalSupply().call(), 0)

        result = self._run_task(subscription)
        self.assertTrue(result["success"], result)

        subscription.refresh_from_db()
        request.refresh_from_db()
        issuance = ShareIssuance.objects.get()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, issuance))
        self.assertEqual(issuance.status, IssuanceStatus.COMPLETED)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 40)
        self.assertEqual(self._contract().functions.totalSupply().call(), 40)

        asset = Asset.get_by_chain_and_contract(SHARE_ASSET_CHAIN, self.token.contract_address)
        holding = Holding.objects.get(wallet=self.wallet, asset=asset)
        self.assertEqual(holding.quantity, Decimal("40"))
        self.assertIsNone(holding.market_value)

    def test_running_the_allotment_twice_in_sequence_mints_exactly_once(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        subscription = self._paid(self._offering(), quantity=25)
        allot(subscription, self.staff)

        first = self._run_task(subscription)
        nonce_after_first = self._signer_nonce()
        second = self._run_task(subscription)

        self.assertTrue(first["success"], first)
        self.assertFalse(second["success"], second)
        self.assertEqual(self._signer_nonce(), nonce_after_first)
        self.assertEqual(ShareIssuance.objects.count(), 1)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 25)
        self.assertEqual(self._contract().functions.totalSupply().call(), 25)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)

    def test_a_second_allot_click_refuses_before_it_reaches_the_chain(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        subscription = self._paid(self._offering(), quantity=10)
        allot(subscription, self.staff)
        self._run_task(subscription)

        blocks_before = self.w3.eth.block_number
        result = allot_batch([Subscription.objects.get(pk=subscription.pk)], self.staff)

        self.assertEqual(result["allotted"], 0)
        self.assertIn("cannot be allotted twice", result["refusals"][0])
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        self.assertEqual(ShareIssuanceRequest.objects.count(), 1)
        self.assertEqual(self._contract().functions.totalSupply().call(), 10)

    def test_a_killed_worker_leaves_the_row_paid_until_reconcile_mirrors_the_executed_request(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        subscription = self._paid(self._offering(), quantity=15)
        allot(subscription, self.staff)

        with patch("offerings.tasks.subscription._mirror_allotted", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._run_task(subscription)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(subscription.issuance_request.status, RequestStatus.EXECUTED)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 15)

        nonce_before = self._signer_nonce()
        self.assertEqual(reconcile_subscriptions(), {"flipped": 1})
        self.assertEqual(self._signer_nonce(), nonce_before)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)
        self.assertEqual(ShareIssuance.objects.count(), 1)
        self.assertEqual(reconcile_subscriptions(), {"flipped": 0})

    def test_a_batch_over_the_chain_headroom_is_refused_whole_and_mints_nothing(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        offering = self._offering()
        Offering.objects.filter(pk=offering.pk).update(cap_shares=CAP * 2)
        offering.refresh_from_db()
        rows = [self._paid(offering, quantity=CAP - 100), self._paid(offering, quantity=200)]

        blocks_before = self.w3.eth.block_number
        result = allot_batch(rows, self.staff)

        self.assertEqual(result["allotted"], 0)
        self.assertIn(f"{CAP} unissued on chain", result["refusals"][0])
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        self.assertFalse(ShareIssuanceRequest.objects.exists())
        self.assertEqual(self._contract().functions.totalSupply().call(), 0)


@chain_available
@override_settings(**CHAIN_SETTINGS)
class SubscriptionAllotmentChainConcurrencyTest(AllotmentChainMixin, APITransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("the compare-and-set claim needs a database that honours row locks")
        super().setUp()

    def test_two_workers_racing_the_same_allotment_mint_exactly_once(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        subscription = self._paid(self._offering(), quantity=30)
        allot(subscription, self.staff)

        nonce_before = self._signer_nonce()
        barrier = threading.Barrier(2)
        results = {}

        def worker(name):
            try:
                barrier.wait(timeout=10)
                results[name] = self._run_task(subscription)
            except BaseException as exc:
                results[name] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(name,)) for name in ("first", "second")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)
        self.assertFalse(any(thread.is_alive() for thread in threads), results)

        successes = [value for value in results.values() if isinstance(value, dict) and value.get("success")]
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(ShareIssuance.objects.count(), 1)
        self.assertEqual(self._signer_nonce(), nonce_before + 1)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 30)
        self.assertEqual(self._contract().functions.totalSupply().call(), 30)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)

    def test_two_operators_clicking_allot_at_once_create_one_issuance_request(self):
        self._deployed()
        WhitelistService().add_to_whitelist(self.investor)
        subscription = self._paid(self._offering(), quantity=20)

        barrier = threading.Barrier(2)
        results = {}

        def worker(name):
            try:
                barrier.wait(timeout=10)
                results[name] = allot(Subscription.objects.get(pk=subscription.pk), self.staff)
            except BaseException as exc:
                results[name] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(name,)) for name in ("first", "second")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertFalse(any(thread.is_alive() for thread in threads), results)

        self.assertEqual(ShareIssuanceRequest.objects.count(), 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.issuance_request, ShareIssuanceRequest.objects.get())

        self.assertTrue(self._run_task(subscription)["success"])
        self.assertEqual(ShareIssuance.objects.count(), 1)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 20)
