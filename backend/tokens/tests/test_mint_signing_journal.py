import json
import signal
import sqlite3
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib import admin
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from web3 import Web3

from integrations.base_chain.client import BaseChainClient
from integrations.base_chain.exceptions import BaseChainTransactionError
from shared.db import atomic
from shared.tests.tenants import make_tenant
from tokens.admin.share_token import ShareIssuanceAdmin
from tokens.exceptions import InvalidTokenStateException
from tokens.models import RequestStatus, ShareIssuance, ShareIssuanceRequest
from tokens.serializers.share_issuance import ShareIssuanceListSerializer
from tokens.services import ShareTokenService

KEY = "0x" + "11" * 32
RECIPIENT = "0x" + "aa" * 20
RECEIPT = {"status": 1, "blockNumber": 9, "gasUsed": 60000}


@override_settings(BLOCKCHAIN_CHAIN_ID=31337, BLOCKCHAIN_OPERATOR_KEY=KEY)
class MintSigningJournalTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("mint-journal")
        self.request = ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address=RECIPIENT,
            amount=10,
            reason="Synthetic mint",
            status=RequestStatus.APPROVED,
        )
        self.chain = object.__new__(BaseChainClient)
        self.chain._web3 = Web3()
        self.chain.assert_expected_chain = Mock(return_value=31337)
        self.chain.load_contract = Mock()
        self.transaction = {
            "from": Account.from_key(KEY).address,
            "to": Web3.to_checksum_address(self.request.token.contract_address),
            "chainId": 31337,
            "nonce": 7,
            "value": 0,
            "gasPrice": 10**9,
            "gas": 100000,
            "data": "0x40c10f19" + "0" * 24 + RECIPIENT[2:] + f"{10:064x}",
        }
        self.raw = Account.sign_transaction(self.transaction, KEY).raw_transaction
        self.tx_hash = Web3.to_hex(Web3.keccak(self.raw))
        self.chain.build_transaction = Mock(return_value=self.transaction)
        self.chain.send_raw_transaction = Mock(return_value=self.tx_hash)
        self.chain.get_transaction_receipt = Mock(return_value=None)
        self.chain.wait_for_receipt = Mock(return_value=RECEIPT)
        patcher = patch("tokens.services.share_token_service.get_base_chain_client", return_value=self.chain)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = ShareTokenService()
        self.service.read_paused = Mock(return_value=False)
        self.service.is_recipient_whitelisted = Mock(return_value=True)
        self.service.share_supply = Mock(return_value=(1000, 0))
        holding = patch.object(ShareTokenService, "_seed_recipient_holding")
        holding.start()
        self.addCleanup(holding.stop)

    def recorded(self):
        return ShareIssuance.objects.get(idempotency_key=self.service.issuance_key(self.request))

    def fail_broadcast(self):
        self.chain.send_raw_transaction.side_effect = RuntimeError("broadcast response lost")
        with self.assertRaisesMessage(RuntimeError, "broadcast response lost"):
            self.service.execute_request(self.request)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.FAILED)
        self.chain.send_raw_transaction.side_effect = None

    def test_the_fixed_hash_and_nonce_are_recorded_before_the_first_broadcast(self):
        def send(raw):
            issuance = self.recorded()
            self.assertEqual(issuance.tx_hash, self.tx_hash)
            self.assertEqual(issuance.mint_journal[-1]["raw_transaction"], Web3.to_hex(raw))
            self.assertEqual(Transaction.from_bytes(raw).nonce, 7)
            return self.tx_hash

        self.chain.send_raw_transaction.side_effect = send
        self.service.execute_request(self.request)
        self.assertEqual(self.request.status, RequestStatus.EXECUTED)
        self.chain.send_raw_transaction.assert_called_once_with(self.raw)

    def test_lost_broadcast_response_retries_only_the_saved_signed_payload(self):
        self.fail_broadcast()
        before = self.recorded().mint_journal
        self.service.execute_request(self.request)

        self.assertEqual(self.request.status, RequestStatus.EXECUTED)
        self.assertEqual(self.chain.build_transaction.call_count, 1)
        self.assertEqual(self.chain.send_raw_transaction.call_count, 2)
        self.assertEqual([call.args[0] for call in self.chain.send_raw_transaction.call_args_list], [self.raw] * 2)
        self.assertEqual(self.recorded().mint_journal, before)

    def test_missing_receipts_and_replay_errors_never_release_or_replace_the_mint(self):
        self.fail_broadcast()
        issuance = self.recorded()
        before = issuance.mint_journal
        for error in ("already known", "nonce too low", "connection lost"):
            with self.subTest(error=error):
                self.chain.send_raw_transaction.side_effect = RuntimeError(error)
                self.assertIsNone(self.service.resolve_executing_issuance(self.request))
                self.request.refresh_from_db()
                issuance.refresh_from_db()
                self.assertEqual(self.request.status, RequestStatus.FAILED)
                self.assertEqual(issuance.tx_hash, self.tx_hash)
                self.assertEqual(issuance.mint_journal, before)
                self.chain.send_raw_transaction.assert_called_with(self.raw)
        self.assertEqual(self.chain.build_transaction.call_count, 1)

    def test_a_failed_journal_write_prevents_broadcast(self):
        with patch("tokens.services.share_token_service.record_signed_mint", side_effect=RuntimeError("write failed")):
            with self.assertRaisesMessage(RuntimeError, "write failed"):
                self.service.execute_request(self.request)
        self.chain.build_transaction.assert_called_once()
        self.chain.send_raw_transaction.assert_not_called()
        self.assertIsNone(self.recorded().tx_hash)

    def test_provider_errors_cannot_publish_the_saved_signed_payload(self):
        raw_hex = Web3.to_hex(self.raw)
        self.chain.send_raw_transaction.side_effect = RuntimeError(f"sendRawTransaction({raw_hex}) rejected")
        with self.assertLogs("tokens.services.share_token_service", level="ERROR") as logs:
            with self.assertRaises(BaseChainTransactionError) as raised:
                self.service.execute_request(self.request)
        self.assertNotIn(raw_hex[2:], str(raised.exception))
        self.assertNotIn(raw_hex[2:], self.recorded().error_message)
        self.assertNotIn(raw_hex[2:], " ".join(logs.output))
        self.assertEqual(self.recorded().mint_journal[-1]["raw_transaction"], raw_hex)

    def test_a_wrapping_transaction_is_refused_before_signing_or_broadcast(self):
        with atomic():
            with self.assertRaisesMessage(RuntimeError, "durable atomic block"):
                self.service.execute_request(self.request)
        self.chain.build_transaction.assert_not_called()
        self.chain.send_raw_transaction.assert_not_called()
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.APPROVED)

    def test_a_superseded_pre_sign_worker_cannot_send_or_fail_the_winner(self):
        actual_mint = self.service._mint_to

        def delay(*args, on_signed):
            self.assertEqual(self.service.resolve_executing_issuance(self.request), "released")
            self.request.refresh_from_db()
            with patch.object(self.service, "_mint_to", wraps=actual_mint):
                self.service.execute_request(self.request)
            on_signed(self.tx_hash, self.raw)

        with patch.object(self.service, "_mint_to", side_effect=delay):
            with self.assertRaisesMessage(InvalidTokenStateException, "no longer current"):
                self.service.execute_request(self.request)

        self.request.refresh_from_db()
        issuance = self.recorded()
        self.assertEqual((self.request.status, issuance.status), ("executed", "completed"))
        self.assertTrue(issuance.mint_journal[0]["abandoned"])
        self.assertEqual(len(issuance.mint_journal), 2)
        self.assertEqual(issuance.mint_journal[1]["tx_hash"], self.tx_hash)
        self.assertNotEqual(issuance.mint_journal[0]["id"], issuance.mint_journal[1]["id"])
        self.chain.send_raw_transaction.assert_called_once_with(self.raw)

    def test_a_legacy_hashless_failed_request_cannot_be_minted_again(self):
        self.request.mark_failed("legacy ambiguous send")
        issuance = ShareIssuance.objects.create(
            token=self.request.token,
            recipient_address=RECIPIENT,
            amount="10",
            status="failed",
            idempotency_key=self.service.issuance_key(self.request),
        )
        self.assertIsNone(issuance.mint_journal)
        with self.assertRaisesMessage(InvalidTokenStateException, "legacy issuance"):
            self.service.execute_request(self.request)
        self.chain.send_raw_transaction.assert_not_called()
        self.assertIsNone(self.service.resolve_executing_issuance(self.request))

    def test_a_corrupt_journal_is_refused_without_signing_a_replacement(self):
        self.fail_broadcast()
        self.assertIsNone(self.service.resolve_executing_issuance(self.request))
        self.chain.send_raw_transaction.assert_called_with(self.raw)
        issuance = self.recorded()
        issuance.mint_journal[-1]["raw_transaction"] = "0x1234"
        issuance.save(update_fields=["mint_journal"])
        self.chain.send_raw_transaction.reset_mock()
        with self.assertRaisesMessage(InvalidTokenStateException, "does not match"):
            self.service.resolve_executing_issuance(self.request)
        self.chain.send_raw_transaction.assert_not_called()
        self.assertEqual(self.chain.build_transaction.call_count, 1)

    def test_reverted_attempts_keep_their_signed_history_when_a_new_attempt_succeeds(self):
        self.fail_broadcast()
        before = self.recorded().mint_journal[0].copy()
        self.chain.get_transaction_receipt.return_value = {**RECEIPT, "status": 0}
        self.transaction["nonce"] = 8
        next_raw = Account.sign_transaction(self.transaction, KEY).raw_transaction
        next_hash = Web3.to_hex(Web3.keccak(next_raw))
        self.chain.send_raw_transaction.return_value = next_hash
        self.service.execute_request(self.request)
        journal = self.recorded().mint_journal
        self.assertEqual(journal[0], {**before, "reverted": True})
        self.assertEqual(journal[1]["tx_hash"], next_hash)
        self.assertEqual(journal[1]["raw_transaction"], Web3.to_hex(next_raw))
        self.assertEqual(self.request.status, RequestStatus.EXECUTED)

    def test_a_late_receipt_timeout_cannot_fail_an_already_completed_mint(self):
        self.fail_broadcast()

        def complete_then_timeout(tx_hash):
            self.service._complete_issuance(self.request, self.recorded(), self.service._tx_result(tx_hash, RECEIPT))
            raise RuntimeError("older wait timed out")

        self.chain.wait_for_receipt.side_effect = complete_then_timeout
        with self.assertRaisesMessage(RuntimeError, "older wait timed out"):
            self.service.execute_request(self.request)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.EXECUTED)
        self.assertEqual(self.recorded().status, "completed")

    def test_an_old_receipt_cannot_complete_a_new_unsigned_attempt(self):
        self.fail_broadcast()
        old_issuance = self.recorded()
        self.chain.get_transaction_receipt.return_value = {**RECEIPT, "status": 0}
        with patch.object(self.service, "_mint_to", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.service.execute_request(self.request)
        self.assertIsNone(self.recorded().tx_hash)
        with self.assertRaisesMessage(InvalidTokenStateException, "different mint transaction"):
            self.service._complete_issuance(self.request, old_issuance, self.service._tx_result(self.tx_hash, RECEIPT))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.EXECUTING)
        self.assertEqual(self.recorded().status, "processing")

    def test_the_journal_is_not_served_or_editable_in_the_admin(self):
        self.fail_broadcast()
        issuance = self.recorded()
        self.assertIn("tx_hash", ShareIssuanceListSerializer(issuance).data)
        self.assertNotIn("mint_journal", ShareIssuanceListSerializer(issuance).data)
        model_admin = ShareIssuanceAdmin(ShareIssuance, admin.site)
        request = Mock(user=self.tenant.user)
        self.assertNotIn("mint_journal", model_admin.get_form(request, issuance).base_fields)
        self.assertNotIn("mint_journal", model_admin.get_fields(request, issuance))

    def test_new_unsigned_attempts_are_not_offered_legacy_operator_actions(self):
        with patch.object(self.service, "_mint_to", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.service.execute_request(self.request)
        ShareIssuanceRequest.objects.filter(pk=self.request.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        self.request.refresh_from_db()
        self.assertIsNone(self.service.unnamed_mint(self.request))
        self.assertEqual(self.service.resolve_executing_issuance(self.request), "released")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.FAILED)


class KilledMintWorkerTest(SimpleTestCase):

    def assert_recovers_killed_worker(self, phase):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            command = [sys.executable, "-m", "tokens.tests.mint_journal_worker", temporary]
            killed = subprocess.run([*command, phase], capture_output=True, text=True, timeout=45)
            self.assertEqual(killed.returncode, -signal.SIGKILL, killed.stdout + killed.stderr)
            with sqlite3.connect(directory / "mint.sqlite3") as independent:
                tx_hash, journal = independent.execute(
                    "SELECT tx_hash, mint_journal FROM tokens_shareissuance"
                ).fetchone()
                status = independent.execute(
                    "SELECT status FROM tokens_shareissuancerequest WHERE reason = 'Synthetic crash recovery'"
                ).fetchone()[0]
            self.assertEqual(status, "executing")
            self.assertIsNotNone(tx_hash)
            attempt = json.loads(journal)[0]
            self.assertEqual(attempt["tx_hash"], tx_hash)
            raw = Web3.to_bytes(hexstr=attempt["raw_transaction"])
            self.assertEqual(Web3.to_hex(Web3.keccak(raw)), tx_hash)
            self.assertEqual(Transaction.from_bytes(raw).nonce, 7)

            recovered = subprocess.run([*command, "recover"], capture_output=True, text=True, timeout=45)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            ledger = json.loads((directory / "node.json").read_text())
            self.assertEqual(ledger["hashes"], [tx_hash])
            self.assertEqual(len(ledger["broadcasts"]), 2)
            self.assertEqual(set(ledger["broadcasts"]), {attempt["raw_transaction"]})
            with sqlite3.connect(directory / "mint.sqlite3") as independent:
                rows = independent.execute("SELECT status, amount, mint_journal FROM tokens_shareissuance").fetchall()
            self.assertEqual(rows, [("completed", "10", journal)])

    def test_a_hard_kill_before_send_leaves_a_durable_replayable_mint(self):
        self.assert_recovers_killed_worker("before_send")

    def test_a_hard_kill_after_node_acceptance_replays_without_minting_twice(self):
        self.assert_recovers_killed_worker("after_send")
