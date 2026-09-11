import os
import signal
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.conf import settings
from django.db import DatabaseError, connections
from rest_framework.test import APITransactionTestCase

from assets.models import Asset, AssetChainDeployment
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
from wallets.models import Holding, Transaction, Wallet, WalletSubmission
from wallets.services import transaction_confirmation, transfers
from wallets.services.submissions import attempt_submission
from wallets.services.sync import _process_transactions
from wallets.tasks.submissions import recover_wallet_submissions
from wallets.tests.test_submission_durability import SubmissionFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"


def terminate_submission(wallet_id, principal_id, signed_raw, phase, sent_path):
    connections.close_all()
    with acting_for(principal_id):
        wallet = Wallet.objects.get(pk=wallet_id)
        provider = Mock(
            spec=["assert_expected_chain", "get_mined_nonce", "get_transaction_receipt", "broadcast_transaction"]
        )
        provider.assert_expected_chain.return_value = settings.BLOCKCHAIN_CHAIN_ID
        provider.get_transaction_receipt.return_value = None
        provider.get_mined_nonce.side_effect = lambda address: {
            "chain_id": provider.assert_expected_chain.return_value,
            "nonce": 0,
            "balance_wei": str(10 * 10**18),
            "block_number": 100,
            "block_hash": "0x" + "ab" * 32,
        }

        def connect(chain):
            if phase == "before_send" and WalletSubmission.objects.filter(wallet=wallet).exists():
                os._exit(23)
            return provider

        def send(raw):
            Path(sent_path).write_bytes(bytes.fromhex(raw.removeprefix("0x")))
            os._exit(23)

        provider.broadcast_transaction.side_effect = send
        with patch("wallets.services.submissions.get_blockchain_client", side_effect=connect):
            transfers.broadcast_transfer(wallet, signed_raw, principal_id=principal_id)
    os._exit(24)


class SubmissionRecoveryChecks(SubmissionFixture):
    def test_token_intent_keeps_its_deployment_scale_when_catalogue_metadata_changes(self):
        contract = self.signer.address
        with use_operator():
            asset = Asset.objects.create(
                symbol="JUSD", name="Journal test token", asset_type="erc20_token", decimals=18, is_verified=True
            )
            deployment = AssetChainDeployment.objects.create(
                asset=asset, chain="base", contract_address=contract, decimals=6
            )
            Holding.objects.create(wallet=self.wallet, asset=asset, quantity=Decimal("10"))
        data = (
            bytes.fromhex("a9059cbb") + bytes(12) + bytes.fromhex(self.recipient[2:]) + (1_500_000).to_bytes(32, "big")
        )
        signed = self.signed(to=contract, value=0, data=data, gas=90000)
        provider = self.provider(signed)
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            result = self.submit_direct(signed)
            submission = self.submission()
            self.assertEqual((submission.asset_id, submission.deployment_id), (asset.pk, deployment.pk))
            self.assertEqual(
                (submission.intent["amount"], submission.intent["raw_amount"], submission.intent["asset_decimals"]),
                ("1.500000", "1500000", 6),
            )
            before = self.financial_state()
            with use_operator():
                AssetChainDeployment.objects.filter(pk=deployment.pk).update(decimals=2)
                Asset.objects.filter(pk=asset.pk).update(decimals=8)
            self.assertEqual(self.submit_direct(signed), result)
            self.assertEqual(self.financial_state(), before)
        self.assertEqual(
            [call.args[0] for call in provider.broadcast_transaction.call_args_list],
            [signed.raw_transaction.to_0x_hex()] * 2,
        )

    def test_direct_token_admission_refuses_an_unverified_asset_with_a_valid_signed_envelope(self):
        with use_operator():
            asset = Asset.objects.create(
                symbol="JUNK",
                name="Unverified journal test token",
                asset_type="erc20_token",
                decimals=6,
                is_verified=False,
            )
            AssetChainDeployment.objects.create(
                asset=asset, chain="base", contract_address=self.signer.address, decimals=6
            )
        data = (
            bytes.fromhex("a9059cbb") + bytes(12) + bytes.fromhex(self.recipient[2:]) + (1_500_000).to_bytes(32, "big")
        )
        signed = self.signed(to=self.signer.address, value=0, data=data, gas=90000)
        with patch("wallets.services.submissions.get_blockchain_client") as connect:
            with self.assertRaisesRegex(InvalidTransactionException, "not a verified asset"):
                self.submit_direct(signed)
            connect.assert_not_called()
        self.assertEqual(self.transactions(), [])

    def test_recovery_never_sends_to_another_chain_or_past_a_visible_receipt(self):
        signed = self.signed()
        provider = self.provider(signed)
        provider.assert_expected_chain.side_effect = [settings.BLOCKCHAIN_CHAIN_ID, settings.BLOCKCHAIN_CHAIN_ID + 1]
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            self.submit_direct(signed)
            provider.broadcast_transaction.assert_not_called()
            submission = self.submission()
            self.assertIsNone(submission.acknowledged_at)
            before = self.financial_state()
            provider.assert_expected_chain.side_effect = None
            provider.assert_expected_chain.return_value = settings.BLOCKCHAIN_CHAIN_ID
            for receipt, expected in (
                ({"transactionHash": signed.hash.to_0x_hex(), "status": 1}, "receipt_available"),
                ({"transactionHash": "0x" + "98" * 32, "status": 1}, "receipt_identity_unavailable"),
                ({"status": 1}, "receipt_identity_unavailable"),
                (False, "receipt_identity_unavailable"),
            ):
                with self.subTest(receipt=receipt), acting_for(self.tenant.user.pk):
                    provider.get_transaction_receipt.return_value = receipt
                    self.assertEqual(attempt_submission(submission.pk), expected)
                    provider.broadcast_transaction.assert_not_called()
            self.assertEqual(self.financial_state(), before)
            provider.get_transaction_receipt.return_value = None
            with acting_for(self.tenant.user.pk):
                self.assertEqual(attempt_submission(submission.pk), "acknowledged")
            provider.broadcast_transaction.assert_called_once_with(signed.raw_transaction.to_0x_hex())

    def test_wallet_deletion_preserves_the_submission_and_its_financial_records(self):
        signed = self.signed()
        with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)):
            self.submit_direct(signed)
        before = self.financial_state()
        self.assertEqual(self.client.delete(f"/api/wallets/{self.wallet.pk}/").status_code, 409)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(self.submission().tx_hash, signed.hash.to_0x_hex())

    def test_exact_retries_never_create_another_debit_and_a_terminal_retry_never_sends(self):
        signed = self.signed()
        provider = self.provider(signed)
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            first = self.submit_direct(signed)
            before = self.financial_state()
            self.assertEqual(self.submit_direct(signed), first)
            self.assertEqual(self.financial_state(), before)
            with use_operator():
                Transaction.objects.filter(wallet=self.wallet, tx_hash=first["txHash"]).update(status="failed")
            after_failure = self.financial_state()
            provider.reset_mock()
            self.assertEqual(self.submit_direct(signed)["status"], "failed")
            provider.broadcast_transaction.assert_not_called()
            self.assertEqual(self.financial_state(), after_failure)
        with use_operator():
            self.assertEqual(WalletSubmission.objects.filter(wallet=self.wallet).count(), 1)

    def test_different_signed_bytes_at_a_recorded_nonce_are_refused_before_rpc(self):
        signed = self.signed()
        provider = self.provider(signed)
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider) as connect:
            self.submit_direct(signed)
            before = self.financial_state()
            connect.reset_mock()
            with self.assertRaisesRegex(InvalidTransactionException, "preserve the original transfer"):
                self.submit_direct(self.signed(value=3 * 10**18))
            connect.assert_not_called()
        self.assertEqual(self.financial_state(), before)

    def test_history_without_a_submission_is_not_adopted_or_broadcast(self):
        signed = self.signed()
        with acting_for(self.tenant.user.pk):
            _process_transactions(
                self.wallet,
                [
                    {
                        "tx_hash": signed.hash.to_0x_hex(),
                        "chain": self.wallet.chain,
                        "from_address": self.wallet.address,
                        "to_address": self.recipient,
                        "amount": "900",
                        "block_timestamp": None,
                        "block_number": None,
                    }
                ],
            )
        before = self.financial_state()
        with patch("wallets.services.submissions.get_blockchain_client") as connect:
            with self.assertRaisesRegex(InvalidTransactionException, "history without a signed submission"):
                self.submit_direct(signed)
            connect.assert_not_called()
        self.assertEqual(self.financial_state(), before)

    def test_a_caller_transaction_cannot_roll_back_an_already_sent_submission(self):
        with (
            acting_for(self.tenant.user.pk),
            atomic(),
            patch("wallets.services.submissions.get_blockchain_client") as connect,
        ):
            with self.assertRaisesRegex(RuntimeError, "durable atomic block cannot be nested"):
                transfers.broadcast_transfer(
                    self.wallet, self.signed().raw_transaction.to_0x_hex(), principal_id=self.tenant.user.pk
                )
            connect.assert_not_called()
        self.assertEqual(self.transactions(), [])

    def test_queue_failure_is_recovered_using_the_identical_signed_bytes(self):
        signed = self.signed()
        provider = self.provider(signed)
        provider.broadcast_transaction.side_effect = TimeoutError("Synthetic lost acknowledgement")
        with (
            patch("wallets.services.submissions.get_blockchain_client", return_value=provider),
            patch(
                "wallets.services.transfers._schedule_confirmation_checks",
                side_effect=RuntimeError("Synthetic queue outage"),
            ),
        ):
            self.assertEqual(self.submit_direct(signed)["status"], "pending")
            before = self.financial_state()
            provider.broadcast_transaction.side_effect = None
            result = recover_wallet_submissions(0)
        self.assertEqual(result, {"attempted": 1, "outcomes": {"acknowledged": 1}})
        self.assertEqual(self.financial_state(), before)
        self.assertIsNotNone(self.submission().acknowledged_at)
        self.assertEqual(
            [call.args[0] for call in provider.broadcast_transaction.call_args_list],
            [signed.raw_transaction.to_0x_hex()] * 2,
        )

    def test_fee_caps_come_from_each_supported_signed_envelope(self):
        for nonce, fields, expected in (
            (0, {}, Decimal("0.000042")),
            (1, {"type": 1, "accessList": []}, Decimal("0.000042")),
            (2, {"type": 2, "maxFeePerGas": 7 * 10**9, "maxPriorityFeePerGas": 10**9}, Decimal("0.000147")),
        ):
            with self.subTest(envelope=fields.get("type")):
                signed = self.signed(nonce=nonce, **fields)
                with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)):
                    response = self.broadcast(signed, transaction_fee="999")
                self.assertEqual(response.status_code, 200)
                with use_operator():
                    tx = Transaction.objects.get(wallet=self.wallet, tx_hash=signed.hash.to_0x_hex())
                self.assertEqual((tx.transaction_fee_estimated, tx.nonce), (expected, nonce))

    def test_foreign_principals_cannot_submit_or_read_signed_bytes(self):
        signed = self.signed()
        with use_operator():
            foreign = make_tenant("submission-foreign")
        with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)) as connect:
            self.client.force_authenticate(foreign.user)
            self.assertEqual(self.broadcast(signed).status_code, 404)
            connect.assert_not_called()
            with acting_for(foreign.user.pk):
                with self.assertRaises(Wallet.DoesNotExist):
                    transfers.broadcast_transfer(
                        self.wallet, signed.raw_transaction.to_0x_hex(), principal_id=foreign.user.pk
                    )
            connect.assert_not_called()
            self.submit_direct(signed)
        if POSTGRES and current_alias() == APP_ALIAS:
            with acting_for(foreign.user.pk):
                self.assertEqual(WalletSubmission.objects.filter(wallet=self.wallet).count(), 0)
            with acting_for(self.tenant.user.pk):
                self.assertEqual(
                    WalletSubmission.objects.select_related("transaction", "wallet", "user_account")
                    .filter(wallet=self.wallet)
                    .count(),
                    1,
                )

    @skipUnless(POSTGRES, "Row locks require PostgreSQL")
    def test_concurrent_duplicate_submissions_share_one_intent_and_one_debit(self):
        signed = self.signed()
        gate = Barrier(2)

        def submit():
            try:
                gate.wait(timeout=10)
                return self.submit_direct(signed)
            finally:
                connections.close_all()

        with (
            patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first, second = pool.submit(submit), pool.submit(submit)
            self.assertEqual(first.result(timeout=15), second.result(timeout=15))
        self.assertEqual(len(self.transactions()), 1)
        with use_operator():
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("7.999958"))

    @skipUnless(POSTGRES and hasattr(os, "fork"), "Process recovery requires PostgreSQL and fork")
    def test_process_exit_before_or_after_send_recovers_the_committed_exact_payload(self):
        for nonce, phase in enumerate(("before_send", "after_send")):
            with (
                self.subTest(phase=phase),
                tempfile.TemporaryDirectory(prefix="wallet-submission-process-") as directory,
            ):
                signed = self.signed(nonce=nonce)
                sent_path = Path(directory) / "sent.bin"
                connections.close_all()
                child = os.fork()
                if child == 0:
                    try:
                        terminate_submission(
                            self.wallet.pk, self.tenant.user.pk, signed.raw_transaction.to_0x_hex(), phase, sent_path
                        )
                    finally:
                        os._exit(25)
                exited = False
                try:
                    deadline = monotonic() + 15
                    while monotonic() < deadline:
                        reaped, status = os.waitpid(child, os.WNOHANG)
                        if reaped:
                            exited = True
                            self.assertEqual(os.waitstatus_to_exitcode(status), 23)
                            break
                        sleep(0.01)
                    self.assertTrue(exited, "The submission child did not reach the selected exit boundary")
                finally:
                    if not exited:
                        os.kill(child, signal.SIGKILL)
                        os.waitpid(child, 0)
                self.assertEqual(sent_path.exists(), phase == "after_send")
                if sent_path.exists():
                    self.assertEqual(sent_path.read_bytes(), bytes(signed.raw_transaction))
                with use_operator():
                    submission = WalletSubmission.objects.get(wallet=self.wallet, tx_hash=signed.hash.to_0x_hex())
                self.assertIsNone(submission.acknowledged_at)
                self.assertEqual(bytes(submission.raw_transaction), bytes(signed.raw_transaction))
                before = self.financial_state()
                provider = self.provider(signed)
                with use_operator(), patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
                    self.assertEqual(attempt_submission(submission.pk), "acknowledged")
                provider.broadcast_transaction.assert_called_once_with(signed.raw_transaction.to_0x_hex())
                self.assertEqual(self.financial_state(), before)

    @skipUnless(POSTGRES, "Database immutability guards require PostgreSQL")
    def test_database_guards_preserve_the_journal_wallet_and_transaction_identity(self):
        signed = self.signed()
        with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)):
            self.submit_direct(signed)
        submission = self.submission()
        before = self.financial_state()
        with use_operator():
            for statement, parameters in (
                (
                    "UPDATE wallets_walletsubmission SET raw_transaction = %s WHERE uuid = %s",
                    [b"changed", submission.pk],
                ),
                ("DELETE FROM wallets_walletsubmission WHERE uuid = %s", [submission.pk]),
                ("UPDATE wallets_walletsubmission SET acknowledged_at = NULL WHERE uuid = %s", [submission.pk]),
                ("UPDATE wallets_walletsubmission SET last_attempt_at = NULL WHERE uuid = %s", [submission.pk]),
                (
                    "UPDATE wallets_walletsubmission SET last_attempt_at = last_attempt_at - interval '1 minute' "
                    "WHERE uuid = %s",
                    [submission.pk],
                ),
                ("UPDATE transactions SET amount = amount + 1 WHERE uuid = %s", [submission.transaction_id]),
                (
                    "UPDATE transactions SET transaction_fee_estimated = transaction_fee_estimated + 1 "
                    "WHERE uuid = %s",
                    [submission.transaction_id],
                ),
                ("UPDATE wallets SET address = %s WHERE uuid = %s", [self.recipient, self.wallet.pk]),
            ):
                with self.subTest(statement=statement), self.assertRaises(DatabaseError), atomic():
                    with connections[current_alias()].cursor() as cursor:
                        cursor.execute(statement, parameters)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(bytes(self.submission().raw_transaction), bytes(signed.raw_transaction))


class SubmissionRecoveryTest(SubmissionRecoveryChecks, APITransactionTestCase):
    pass


class ScopedSubmissionRecoveryTest(RunsOnTheScopedConnection, SubmissionRecoveryChecks, APITransactionTestCase):
    pass
