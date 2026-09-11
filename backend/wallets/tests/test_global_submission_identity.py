from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import connections
from rest_framework.test import APITransactionTestCase
from web3 import Web3

from assets.services.identity import native_asset_for_chain
from shared.db import APP_ALIAS, acting_for, configured, current_alias, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Transaction, Wallet, WalletSubmission
from wallets.services import transfers
from wallets.tests.test_submission_durability import SubmissionFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"


class GlobalSubmissionFixture(SubmissionFixture):
    def setUp(self):
        super().setUp()
        with use_operator():
            self.other = make_tenant("global-submission")
            self.other_wallet = Wallet.objects.create(
                user_account=self.other.account,
                address=self.signer.address.lower(),
                chain="base",
                verification_status="VERIFIED",
            )
            self.other_holding = Holding.objects.create(
                wallet=self.other_wallet, asset=self.native, quantity=Decimal("10")
            )
        self.chain_provider = self.provider(self.signed())
        self.chain_provider.broadcast_transaction.side_effect = lambda raw: Web3.keccak(hexstr=raw).to_0x_hex()
        boundary = patch("wallets.services.submissions.get_blockchain_client", return_value=self.chain_provider)
        self.connect = boundary.start()
        self.addCleanup(boundary.stop)

    def submit_as(self, wallet, user, signed):
        with acting_for(user.pk):
            return transfers.broadcast_transfer(wallet, signed.raw_transaction.to_0x_hex(), principal_id=user.pk)

    def all_financial_state(self):
        with use_operator():
            return list(Transaction.objects.order_by("pk").values()), list(Holding.objects.order_by("pk").values())


class GlobalSubmissionIdentityChecks(GlobalSubmissionFixture):
    def test_one_signed_transaction_cannot_be_recorded_by_two_accounts(self):
        signed = self.signed()
        self.submit_direct(signed)
        before = self.all_financial_state()
        self.client.force_authenticate(self.other.user)
        self.connect.reset_mock()
        response = self.client.post(
            f"/api/wallets/{self.other_wallet.pk}/broadcast-transfer/",
            {"signed_transaction": signed.raw_transaction.to_0x_hex()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "This signed transaction or sender nonce is already recorded.")
        self.assertEqual(self.all_financial_state(), before)
        self.connect.assert_not_called()
        if POSTGRES and current_alias() == APP_ALIAS:
            with acting_for(self.other.user.pk):
                self.assertEqual(WalletSubmission.objects.count(), 0)
            with acting_for(self.tenant.user.pk):
                self.assertEqual(WalletSubmission.objects.count(), 1)

    def test_different_signed_terms_cannot_reserve_another_accounts_recorded_sender_nonce(self):
        signed = self.signed()
        self.submit_direct(signed)
        before = self.all_financial_state()
        changed = self.signed(value=3 * 10**18)
        self.connect.reset_mock()
        with self.assertRaisesRegex(InvalidTransactionException, "sender nonce is already recorded"):
            self.submit_as(self.other_wallet, self.other.user, changed)
        self.connect.assert_not_called()
        self.assertEqual(self.all_financial_state(), before)

    def test_own_wallet_retries_and_distinct_nonces_remain_available(self):
        signed = self.signed()
        first = self.submit_direct(signed)
        before = self.all_financial_state()
        self.assertEqual(self.submit_direct(signed), first)
        self.assertEqual(self.all_financial_state(), before)
        other = self.signed(nonce=4)
        self.assertEqual(self.submit_as(self.other_wallet, self.other.user, other)["status"], "pending")
        with use_operator():
            self.assertEqual(WalletSubmission.objects.count(), 2)
            self.other_holding.refresh_from_db()
        self.assertEqual(self.other_holding.quantity, Decimal("7.999958"))

    def test_the_same_signer_nonce_on_different_networks_identifies_distinct_spends(self):
        first = self.signed()
        self.submit_direct(first)
        with use_operator():
            wallet = Wallet.objects.create(
                user_account=self.other.account,
                address=self.signer.address,
                chain="ethereum",
                verification_status="VERIFIED",
            )
            Holding.objects.create(wallet=wallet, asset=native_asset_for_chain("ethereum"), quantity=Decimal("10"))
        self.assertNotEqual(settings.BLOCKCHAIN_CHAIN_ID, settings.ETHEREUM_CHAIN_ID)
        second = self.signed(chainId=settings.ETHEREUM_CHAIN_ID)
        self.chain_provider.assert_expected_chain.return_value = settings.ETHEREUM_CHAIN_ID
        self.assertEqual(self.submit_as(wallet, self.other.user, second)["status"], "pending")
        with use_operator():
            self.assertCountEqual(
                list(WalletSubmission.objects.values_list("chain_id", "nonce")),
                [(settings.BLOCKCHAIN_CHAIN_ID, 3), (settings.ETHEREUM_CHAIN_ID, 3)],
            )
        self.chain_provider.broadcast_transaction.assert_called_with(second.raw_transaction.to_0x_hex())

    @skipUnless(POSTGRES, "Concurrent constraint arbitration requires PostgreSQL")
    def test_concurrent_account_submissions_admit_one_spend_and_one_deduction(self):
        gate = Barrier(2)
        signed = self.signed()
        changed = self.signed(value=3 * 10**18)

        def submit(wallet, user, payload):
            try:
                gate.wait(timeout=10)
                try:
                    return self.submit_as(wallet, user, payload)["status"]
                except InvalidTransactionException:
                    return "refused"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit, self.wallet, self.tenant.user, signed)
            second = pool.submit(submit, self.other_wallet, self.other.user, changed)
            self.assertCountEqual([first.result(timeout=20), second.result(timeout=20)], ["pending", "refused"])
        with use_operator():
            self.assertEqual(WalletSubmission.objects.count(), 1)
            recorded = Transaction.objects.get(wallet__in=[self.wallet, self.other_wallet])
            quantities = list(
                Holding.objects.filter(pk__in=[self.holding.pk, self.other_holding.pk]).values_list(
                    "quantity", flat=True
                )
            )
        self.assertEqual(sum(quantities), Decimal("20") - recorded.amount - Decimal("0.000042"))
        self.assertEqual(self.chain_provider.broadcast_transaction.call_count, 1)


class GlobalSubmissionIdentityTest(GlobalSubmissionIdentityChecks, APITransactionTestCase):
    pass


class ScopedGlobalSubmissionIdentityTest(
    RunsOnTheScopedConnection, GlobalSubmissionIdentityChecks, APITransactionTestCase
):
    pass
