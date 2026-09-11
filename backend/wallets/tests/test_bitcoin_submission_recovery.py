from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import DatabaseError, connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from shared.db import (
    APP_ALIAS,
    acting_for,
    atomic,
    configured,
    current_alias,
    use_operator,
)
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.exceptions import InvalidTransactionException
from wallets.models import (
    BitcoinSubmission,
    BitcoinSubmissionInput,
    Holding,
    Transaction,
    Wallet,
)
from wallets.services import transaction_confirmation
from wallets.services.bitcoin_submissions import attempt_bitcoin_submission
from wallets.services.sync import _process_transactions
from wallets.tasks.submissions import recover_wallet_submissions
from wallets.tests.test_bitcoin_submission import FIXTURE, BitcoinSubmissionFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"


class BitcoinSubmissionRecoveryChecks(BitcoinSubmissionFixture):
    def recover(self):
        with use_operator():
            return attempt_bitcoin_submission(self.submission().pk)

    def permit_conflicting_vector(self):
        alternate = FIXTURE["conflicting_transfer"]
        self.rpc_overrides["testmempoolaccept"] = lambda params: [
            alternate["preflight"] if params[0] == [alternate["raw_transaction"]] else FIXTURE["preflight"]
        ]
        return alternate["raw_transaction"]

    def test_queue_failure_and_lost_response_recover_the_exact_payload_once_without_another_debit(self):
        self.lost_acknowledgement = True
        with patch(
            "wallets.services.transfers._schedule_confirmation_checks", side_effect=RuntimeError("Queue outage")
        ):
            self.assertEqual(self.submit_direct()["status"], "pending")
        before = self.transactions()
        self.assertIsNone(self.submission().acknowledged_at)
        self.lost_acknowledgement = False
        self.assertEqual(recover_wallet_submissions(0), {"attempted": 1, "outcomes": {"acknowledged": 1}})
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]] * 2)
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.quantity(), Decimal("47.9999"))
        self.assertIsNotNone(self.submission().acknowledged_at)

    def test_an_exact_mempool_transaction_resolves_a_lost_acknowledgement_without_another_send(self):
        self.lost_acknowledgement = True
        self.submit_direct()
        self.preflight = {"txid": FIXTURE["txid"], "wtxid": FIXTURE["wtxid"], "allowed": False}
        self.rpc_overrides["getrawtransaction"] = {
            "txid": FIXTURE["txid"],
            "hash": FIXTURE["wtxid"],
            "hex": FIXTURE["raw_transaction"],
        }
        self.rpc_overrides["getmempoolentry"] = {"wtxid": FIXTURE["wtxid"]}
        self.assertEqual(self.recover(), "acknowledged")
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])
        self.assertEqual(self.quantity(), Decimal("47.9999"))

    def test_a_different_witness_in_the_mempool_cannot_acknowledge_the_recorded_payload(self):
        self.lost_acknowledgement = True
        self.submit_direct()
        self.preflight = {"txid": FIXTURE["txid"], "wtxid": FIXTURE["wtxid"], "allowed": False}
        self.rpc_overrides["getrawtransaction"] = {
            "txid": FIXTURE["txid"],
            "hash": FIXTURE["wtxid"],
            "hex": FIXTURE["raw_transaction"],
        }
        self.rpc_overrides["getmempoolentry"] = {"wtxid": "71" * 32}
        self.assertEqual(self.recover(), "delivery_unavailable")
        self.assertIsNone(self.submission().acknowledged_at)
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])

    def test_recovery_checks_the_recorded_network_and_each_previous_output_again(self):
        self.lost_acknowledgement = True
        self.submit_direct()
        before = self.transactions()
        for method, result in (
            ("getblockhash", "91" * 32),
            ("getblockchaininfo", {"chain": "main"}),
            ("gettxout", None),
            ("gettxout", {"scriptPubKey": {"hex": self.input_script}, "value": "49", "bestblock": "48" * 32}),
        ):
            with self.subTest(method=method, result=result):
                self.rpc_overrides = {method: result}
                self.assertIn(self.recover(), {"delivery_unavailable", "input_identity_unavailable"})
                self.assertIsNone(self.submission().acknowledged_at)
                self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.quantity(), Decimal("47.9999"))

    def test_mined_receipts_leave_confirmation_to_the_receipt_writer(self):
        self.lost_acknowledgement = True
        self.submit_direct()
        before = self.transactions()
        self.rpc_overrides["getrawtransaction"] = {"txid": FIXTURE["txid"], "confirmations": 1, "blockhash": "14" * 32}
        self.assertEqual(self.recover(), "receipt_available")
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])
        self.assertIsNone(self.submission().acknowledged_at)

    def test_terminal_retries_never_send_or_recreate_accounting(self):
        self.submit_direct()
        with acting_for(self.tenant.user.pk):
            transaction_confirmation.fail_transaction(FIXTURE["txid"], wallet=self.wallet)
        before = self.transactions()
        self.assertEqual(self.submit_direct()["status"], "failed")
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.quantity(), Decimal("50"))

    def test_history_without_a_submission_is_never_adopted_or_broadcast(self):
        with acting_for(self.tenant.user.pk):
            _process_transactions(
                self.wallet,
                [
                    {
                        "tx_hash": FIXTURE["txid"],
                        "chain": "bitcoin",
                        "from_address": self.wallet.address,
                        "to_address": FIXTURE["recipient"],
                        "amount": "1",
                        "block_timestamp": None,
                        "block_number": None,
                    }
                ],
            )
        before = self.transactions()
        with self.assertRaisesRegex(InvalidTransactionException, "history without a signed submission"):
            self.submit_direct()
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.quantity(), Decimal("50"))

    def test_foreign_principals_and_unverified_wallets_cannot_submit_or_read_raw_bytes(self):
        with use_operator():
            foreign = make_tenant("bitcoin-foreign")
        self.client.force_authenticate(foreign.user)
        self.assertEqual(self.broadcast().status_code, 404)
        with self.assertRaises(InvalidTransactionException):
            self.submit_direct(principal_id=foreign.user.pk)
        self.assertEqual(self.provider._rpc_call.call_count, 0)
        with use_operator():
            Wallet.objects.filter(pk=self.wallet.pk).update(verification_status="PENDING")
        with self.assertRaises(InvalidTransactionException):
            self.submit_direct()
        self.assertEqual(self.provider._rpc_call.call_count, 0)
        with use_operator():
            Wallet.objects.filter(pk=self.wallet.pk).update(verification_status="VERIFIED")
        self.submit_direct()
        if POSTGRES and current_alias() == APP_ALIAS:
            with acting_for(foreign.user.pk):
                self.assertEqual(BitcoinSubmission.objects.count(), 0)
                self.assertEqual(BitcoinSubmissionInput.objects.count(), 0)
            with acting_for(self.tenant.user.pk):
                self.assertEqual(BitcoinSubmission.objects.count(), 1)
                self.assertEqual(BitcoinSubmissionInput.objects.count(), 1)

    def test_the_same_network_transaction_cannot_be_accounted_by_another_account(self):
        self.submit_direct()
        with use_operator():
            foreign = make_tenant("bitcoin-duplicate-owner")
            wallet = Wallet.objects.create(
                user_account=foreign.account,
                chain="bitcoin",
                address=self.wallet.address,
                verification_status="VERIFIED",
            )
            holding = Holding.objects.create(wallet=wallet, asset=self.asset, quantity=Decimal("50"))
        alternate = self.permit_conflicting_vector()
        for raw in (FIXTURE["raw_transaction"], alternate):
            with self.subTest(raw=raw), self.assertRaisesRegex(InvalidTransactionException, "already recorded"):
                self.submit_direct(raw, wallet=wallet, principal_id=foreign.user.pk)
        with use_operator():
            holding.refresh_from_db()
            self.assertEqual(holding.quantity, Decimal("50"))
            self.assertEqual(Transaction.objects.filter(wallet=wallet).count(), 0)
            self.assertEqual(BitcoinSubmission.objects.count(), 1)
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])

    def test_conflicting_inputs_cannot_create_a_second_intent_or_deduction(self):
        self.submit_direct()
        before = self.transactions()
        alternate = self.permit_conflicting_vector()
        with self.assertRaisesRegex(InvalidTransactionException, "already recorded"):
            self.submit_direct(alternate)
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.quantity(), Decimal("47.9999"))
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]])

    def test_altered_witness_bytes_at_the_same_txid_are_refused_without_rpc(self):
        self.submit_direct()
        changed = bytearray.fromhex(FIXTURE["raw_transaction"])
        changed[-10] ^= 1
        before = self.transactions()
        self.provider._rpc_call.reset_mock()
        with self.assertRaisesRegex(InvalidTransactionException, "Different Bitcoin witness bytes"):
            self.submit_direct(changed.hex())
        self.provider._rpc_call.assert_not_called()
        self.assertEqual(self.transactions(), before)

    def test_provider_numbers_and_identity_are_strict_before_any_financial_effect(self):
        for value in (True, 50.0, "NaN", "-1", "50.000000001", "50.00000000000000000000000000001", "1e1000000"):
            with self.subTest(value=value):
                self.rpc_overrides["gettxout"] = {
                    "scriptPubKey": {"hex": self.input_script},
                    "value": value,
                    "bestblock": "48" * 32,
                }
                with self.assertRaises(InvalidTransactionException):
                    self.submit_direct()
        self.rpc_overrides = {}
        for fields in ({"txid": "82" * 32}, {"wtxid": "83" * 32}, {"allowed": 1}, {"fees": {"base": "0.1"}}):
            with self.subTest(fields=fields):
                self.preflight = {**FIXTURE["preflight"], **fields}
                with self.assertRaises(InvalidTransactionException):
                    self.submit_direct()
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.transactions(), [])
        self.assertEqual(self.quantity(), Decimal("50"))

    def test_a_wallet_change_during_preflight_requires_a_fresh_submission(self):
        def change_wallet(params):
            with use_operator():
                Wallet.objects.filter(pk=self.wallet.pk).update(address=FIXTURE["recipient"])
            return [FIXTURE["preflight"]]

        self.rpc_overrides["testmempoolaccept"] = change_wallet
        with self.assertRaisesRegex(InvalidTransactionException, "wallet changed"):
            self.submit_direct()
        self.assertEqual(self.transactions(), [])
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.quantity(), Decimal("50"))

    @skipUnless(POSTGRES, "Row locks require PostgreSQL")
    def test_another_database_connection_sees_every_record_and_the_debit_before_send(self):
        observed = []

        def read_committed():
            try:
                with use_operator():
                    return (
                        Transaction.objects.filter(wallet=self.wallet).count(),
                        BitcoinSubmission.objects.filter(wallet=self.wallet).count(),
                        BitcoinSubmissionInput.objects.filter(submission__wallet=self.wallet).count(),
                        Holding.objects.get(pk=self.holding.pk).quantity,
                    )
            finally:
                connections.close_all()

        def observe(raw):
            with ThreadPoolExecutor(max_workers=1) as pool:
                observed.append(pool.submit(read_committed).result(timeout=10))

        self.before_send = observe
        self.assertEqual(self.submit_direct()["status"], "pending")
        self.assertEqual(observed, [(1, 1, 1, Decimal("47.9999"))])

    @skipUnless(POSTGRES, "Row locks require PostgreSQL")
    def test_concurrent_exact_retries_share_one_durable_intent_and_one_debit(self):
        gate = Barrier(2)

        def submit():
            try:
                gate.wait(timeout=10)
                return self.submit_direct()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(submit), pool.submit(submit)
            self.assertEqual(first.result(timeout=20), second.result(timeout=20))
        self.assertEqual(len(self.transactions()), 1)
        self.assertEqual(self.quantity(), Decimal("47.9999"))
        with use_operator():
            self.assertEqual(BitcoinSubmissionInput.objects.count(), 1)

    @skipUnless(POSTGRES, "Row locks require PostgreSQL")
    def test_concurrent_conflicting_inputs_admit_only_one_signed_intent(self):
        alternate = self.permit_conflicting_vector()
        gate = Barrier(2)

        def submit(raw):
            try:
                gate.wait(timeout=10)
                try:
                    return self.submit_direct(raw)["status"]
                except InvalidTransactionException:
                    return "refused"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(submit, FIXTURE["raw_transaction"]), pool.submit(submit, alternate)
            self.assertCountEqual([first.result(timeout=20), second.result(timeout=20)], ["pending", "refused"])
        transactions = self.transactions()
        self.assertEqual(len(transactions), 1)
        self.assertEqual(self.quantity(), Decimal("50") - transactions[0]["amount"] - Decimal("0.0001"))
        self.assertEqual(len(self.sent()), 1)
        with use_operator():
            self.assertEqual(BitcoinSubmissionInput.objects.count(), 1)

    @skipUnless(POSTGRES, "Database guards require PostgreSQL")
    def test_database_guards_preserve_intent_inputs_wallet_identity_and_delivery_evidence(self):
        self.submit_direct()
        submission = self.submission()
        before = self.transactions()
        with use_operator():
            item = BitcoinSubmissionInput.objects.get(submission=submission)
            for statement, parameters in (
                (
                    "UPDATE wallets_bitcoinsubmission SET raw_transaction = %s WHERE uuid = %s",
                    [bytes(12), submission.pk],
                ),
                ("DELETE FROM wallets_bitcoinsubmission WHERE uuid = %s", [submission.pk]),
                ("UPDATE wallets_bitcoinsubmission SET acknowledged_at = NULL WHERE uuid = %s", [submission.pk]),
                (
                    "UPDATE wallets_bitcoinsubmission SET last_attempt_at = %s WHERE uuid = %s",
                    [timezone.now() - timezone.timedelta(days=1), submission.pk],
                ),
                ("UPDATE wallets_bitcoinsubmissioninput SET satoshis = 1 WHERE uuid = %s", [item.pk]),
                ("DELETE FROM wallets_bitcoinsubmissioninput WHERE uuid = %s", [item.pk]),
                ("UPDATE transactions SET amount = 8 WHERE uuid = %s", [submission.transaction_id]),
                ("UPDATE wallets SET address = %s WHERE uuid = %s", [FIXTURE["recipient"], self.wallet.pk]),
            ):
                with self.subTest(statement=statement), self.assertRaises(DatabaseError), atomic():
                    with connections[current_alias()].cursor() as cursor:
                        cursor.execute(statement, parameters)
            self.assertEqual(
                bytes(BitcoinSubmission.objects.get(pk=submission.pk).raw_transaction),
                bytes.fromhex(FIXTURE["raw_transaction"]),
            )
        self.assertEqual(self.transactions(), before)
        self.assertEqual(self.quantity(), Decimal("47.9999"))


@override_settings(BITCOIN_NETWORK="regtest")
class BitcoinSubmissionRecoveryTest(BitcoinSubmissionRecoveryChecks, APITransactionTestCase):
    pass


@override_settings(BITCOIN_NETWORK="regtest")
class ScopedBitcoinSubmissionRecoveryTest(
    RunsOnTheScopedConnection, BitcoinSubmissionRecoveryChecks, APITransactionTestCase
):
    pass
