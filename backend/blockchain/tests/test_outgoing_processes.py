import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import skipUnless

from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from eth_account._utils.legacy_transactions import Transaction
from web3 import Web3

from blockchain.models import (
    OutgoingOperation,
    OutgoingStatus,
    SignedAttempt,
    SignerAdmission,
    SigningAccount,
)
from blockchain.services.outgoing import (
    OutgoingTransactionError,
    close_signer_admission,
    prepare_operation,
)
from blockchain.tests.outgoing_fixtures import (
    CHAIN_ID,
    SENDER,
    admitted_signer,
    chain_client,
    claim_operation,
)


def worker(directory, phase, index=0, database=None):
    env = os.environ.copy()
    if database:
        env["OUTGOING_TEST_DATABASE"] = json.dumps(database)
    return subprocess.Popen(
        [sys.executable, "-m", "blockchain.tests.outgoing_worker", str(directory), phase, str(index)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish(process):
    try:
        out, err = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        raise AssertionError(f"Synthetic worker timed out: {out}\n{err}") from None
    return process.returncode, out, err


class OutgoingCrashRecoveryTest(SimpleTestCase):
    def crashed_then_recovered(self, phase):
        with tempfile.TemporaryDirectory(prefix="outgoing-crash-") as temporary:
            directory = Path(temporary)
            code, out, err = finish(worker(directory, phase))
            self.assertEqual(code, -signal.SIGKILL, out + err)
            with sqlite3.connect(directory / "outgoing.sqlite3") as independent:
                attempts = independent.execute(
                    "SELECT tx_hash, raw_transaction, nonce FROM blockchain_signedattempt"
                ).fetchall()
                accounts = independent.execute("SELECT next_nonce FROM blockchain_signingaccount").fetchall()
                status, attempt_id = independent.execute(
                    "SELECT status, current_attempt_id FROM blockchain_outgoingoperation"
                ).fetchone()
            if phase == "before_commit":
                self.assertEqual(attempts, [])
                self.assertEqual(accounts, [(0,)])
                self.assertEqual((status, attempt_id), ("preparing", None))
            else:
                self.assertEqual(len(attempts), 1)
                tx_hash, raw, nonce = attempts[0]
                self.assertEqual(Web3.to_hex(Web3.keccak(raw)), tx_hash)
                self.assertEqual(Transaction.from_bytes(raw).nonce, nonce)
                self.assertEqual((nonce, accounts, status), (7, [(8,)], "signed"))
                self.assertIsNotNone(attempt_id)
            code, out, err = finish(worker(directory, "recover"))
            self.assertEqual(code, 0, out + err)
            ledger = json.loads((directory / "node.json").read_text())
            self.assertEqual(len(ledger["hashes"]), 1)
            self.assertEqual(len(set(ledger["broadcasts"])), 1)
            self.assertEqual(len(ledger["broadcasts"]), 2 if phase == "after_send" else 1)
            with sqlite3.connect(directory / "outgoing.sqlite3") as independent:
                self.assertEqual(
                    independent.execute("SELECT status FROM blockchain_outgoingoperation").fetchone(), ("confirmed",)
                )
                self.assertEqual(independent.execute("SELECT count(*) FROM blockchain_signedattempt").fetchone(), (1,))
                self.assertEqual(
                    independent.execute("SELECT next_nonce FROM blockchain_signingaccount").fetchone(), (8,)
                )

    def test_killed_before_commit_leaves_no_signed_attempt_or_nonce_reservation(self):
        self.crashed_then_recovered("before_commit")

    def test_killed_after_commit_before_send_replays_the_durable_signed_attempt(self):
        self.crashed_then_recovered("before_send")

    def test_killed_after_node_acceptance_replays_identical_bytes_and_changes_the_chain_once(self):
        self.crashed_then_recovered("after_send")


@skipUnless(connection.vendor == "postgresql", "Independent signer row locks require PostgreSQL")
class OutgoingProcessRaceTest(TransactionTestCase):
    def setUp(self):
        admitted_signer()

    def database(self):
        fields = ("ENGINE", "NAME", "USER", "PASSWORD", "HOST", "PORT", "OPTIONS")
        return {key: connection.settings_dict[key] for key in fields}

    def wait_for_files(self, directory, pattern, count):
        until = time.monotonic() + 20
        while len(list(directory.glob(pattern))) < count and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(len(list(directory.glob(pattern))), count)

    def run_race(self, indices):
        with tempfile.TemporaryDirectory(prefix="outgoing-race-") as temporary:
            directory = Path(temporary)
            processes = [worker(directory, "race", index, self.database()) for index in indices]
            try:
                self.wait_for_files(directory, "ready-*", len(processes))
                (directory / "go").touch()
                self.wait_for_files(directory, "signing-*", 1)
                time.sleep(0.2)
                self.assertEqual(len(list(directory.glob("signing-*"))), 1)
                (directory / "sign").touch()
                answers = []
                for process in processes:
                    code, out, err = finish(process)
                    self.assertEqual(code, 0, out + err)
                    answers.append(json.loads(out.strip()))
                return answers
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_independent_processes_share_one_signer_and_reserve_distinct_nonces(self):
        results = self.run_race(range(4))
        self.assertEqual(sorted(row["nonce"] for row in results), [7, 8, 9, 10])
        self.assertEqual(len({row["hash"] for row in results}), 4)
        self.assertEqual(SigningAccount.objects.get().next_nonce, 11)
        self.assertEqual(SignedAttempt.objects.count(), 4)

    def test_two_processes_preparing_one_operation_return_the_same_signed_attempt(self):
        results = self.run_race([0, 0])
        self.assertEqual(results[0], results[1])
        self.assertEqual(SigningAccount.objects.get().next_nonce, 8)
        self.assertEqual(SignedAttempt.objects.count(), 1)

    def test_a_blocked_broadcast_does_not_hold_the_signer_lock(self):
        with tempfile.TemporaryDirectory(prefix="outgoing-wait-") as temporary:
            directory = Path(temporary)
            blocked = worker(directory, "blocked_send", 0, self.database())
            try:
                self.wait_for_files(directory, "sending", 1)
                code, out, err = finish(worker(directory, "sign", 1, self.database()))
                self.assertEqual(code, 0, out + err)
                self.assertEqual(json.loads(out)["nonce"], 8)
                self.assertIsNone(blocked.poll())
                (directory / "release").touch()
                code, out, err = finish(blocked)
                self.assertEqual(code, 0, out + err)
            finally:
                if blocked.poll() is None:
                    blocked.kill()
                    blocked.communicate()

    def test_a_paused_process_cannot_sign_after_close_and_synthetic_readmission(self):
        with tempfile.TemporaryDirectory(prefix="outgoing-admission-generation-") as temporary:
            directory = Path(temporary)
            delayed = worker(directory, "admission_wait", database=self.database())
            try:
                self.wait_for_files(directory, "ready-*", 1)
                self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 2)
                SigningAccount.objects.update(admission_state=SignerAdmission.ADMITTED, admission_generation=3)
                (directory / "go").touch()
                code, out, err = finish(delayed)
                self.assertEqual(code, 0, out + err)
                self.assertIn("generation has changed", json.loads(out)["refused"])
                self.assertFalse((directory / "signed").exists())
                self.assertFalse(SignedAttempt.objects.exists())
                self.assertEqual(SigningAccount.objects.get().next_nonce, 0)
                code, out, err = finish(worker(directory, "sign", 1, self.database()))
                self.assertEqual(code, 0, out + err)
                self.assertEqual(json.loads(out)["nonce"], 7)
            finally:
                if delayed.poll() is None:
                    delayed.kill()
                    delayed.communicate()

    def test_closure_winning_before_a_paused_signer_creates_no_signed_attempt(self):
        with tempfile.TemporaryDirectory(prefix="outgoing-admission-close-first-") as temporary:
            directory = Path(temporary)
            delayed = worker(directory, "admission_wait", database=self.database())
            try:
                self.wait_for_files(directory, "ready-*", 1)
                code, out, err = finish(worker(directory, "close_admission", database=self.database()))
                self.assertEqual(code, 0, out + err)
                self.assertEqual(json.loads(out)["generation"], 2)
                (directory / "go").touch()
                code, out, err = finish(delayed)
                self.assertEqual(code, 0, out + err)
                self.assertIn("admission is closed", json.loads(out)["refused"])
                self.assertFalse((directory / "signed").exists())
                self.assertFalse(SignedAttempt.objects.exists())
                self.assertEqual(SigningAccount.objects.get().next_nonce, 0)
                self.assertEqual(OutgoingOperation.objects.get().status, OutgoingStatus.PREPARING)
            finally:
                if delayed.poll() is None:
                    delayed.kill()
                    delayed.communicate()

    def test_closure_waits_for_local_signing_to_commit_its_payload_and_nonce(self):
        with tempfile.TemporaryDirectory(prefix="outgoing-admission-sign-first-") as temporary:
            directory = Path(temporary)
            signing = worker(directory, "admission_sign", database=self.database())
            closing = None
            try:
                self.wait_for_files(directory, "ready-*", 1)
                (directory / "go").touch()
                self.wait_for_files(directory, "signing-*", 1)
                closing = worker(directory, "close_admission", database=self.database())
                self.wait_for_files(directory, "closing", 1)
                backend_pid = int((directory / "closing").read_text())
                until = time.monotonic() + 10
                blocked = False
                while time.monotonic() < until and closing.poll() is None:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [backend_pid])
                        blocked = cursor.fetchone() == ("Lock",)
                    if blocked:
                        break
                    time.sleep(0.01)
                self.assertTrue(blocked, "The close process must wait on the signing transaction's row lock")
                self.assertFalse((directory / "closed").exists())
                self.assertIsNone(closing.poll())
                (directory / "sign").touch()
                code, out, err = finish(signing)
                self.assertEqual(code, 0, out + err)
                tx_hash = json.loads(out)["hash"]
                code, out, err = finish(closing)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(json.loads(out)["generation"], 2)
                attempt = SignedAttempt.objects.get()
                self.assertEqual(Web3.to_hex(Web3.keccak(bytes(attempt.raw_transaction))), tx_hash)
                signer = SigningAccount.objects.get()
                self.assertEqual((signer.admission_state, signer.next_nonce), (SignerAdmission.CLOSED, 8))
                self.assertEqual(OutgoingOperation.objects.get().current_attempt_id, attempt.pk)
            finally:
                for process in (signing, closing):
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_closing_does_not_cancel_an_already_admitted_inflight_send(self):
        with tempfile.TemporaryDirectory(prefix="outgoing-admission-inflight-") as temporary:
            directory = Path(temporary)
            sending = worker(directory, "blocked_send", database=self.database())
            try:
                self.wait_for_files(directory, "sending", 1)
                self.assertEqual(close_signer_admission(chain_id=CHAIN_ID, sender=SENDER), 2)
                self.assertIsNone(sending.poll())
                client = chain_client()
                with self.assertRaisesMessage(OutgoingTransactionError, "admission is closed"):
                    prepare_operation(claim_operation("closed-after-admission"), client)
                self.assertEqual(client.mock_calls, [])
                (directory / "release").touch()
                code, out, err = finish(sending)
                self.assertEqual(code, 0, out + err)
                ledger = json.loads((directory / "node.json").read_text())
                self.assertEqual(len(ledger["broadcasts"]), 1)
                attempt = SignedAttempt.objects.get()
                self.assertEqual(ledger["broadcasts"][0], Web3.to_hex(bytes(attempt.raw_transaction)))
                self.assertEqual(attempt.operation.status, OutgoingStatus.CONFIRMED)
                signer = SigningAccount.objects.get()
                self.assertEqual((signer.admission_state, signer.next_nonce), (SignerAdmission.CLOSED, 8))
            finally:
                if sending.poll() is None:
                    sending.kill()
                    sending.communicate()

    def recover_postgresql_crash(self, phase):
        with tempfile.TemporaryDirectory(prefix="outgoing-pg-crash-") as temporary:
            directory = Path(temporary)
            code, out, err = finish(worker(directory, phase, database=self.database()))
            self.assertEqual(code, -signal.SIGKILL, out + err)
            operation = OutgoingOperation.objects.get()
            if phase == "before_commit":
                self.assertEqual(operation.status, OutgoingStatus.PREPARING)
                self.assertIsNone(operation.current_attempt_id)
                self.assertFalse(SignedAttempt.objects.exists())
                self.assertEqual(SigningAccount.objects.get().next_nonce, 0)
            else:
                attempt = operation.current_attempt
                self.assertEqual(operation.status, OutgoingStatus.SIGNED)
                self.assertEqual(Web3.to_hex(Web3.keccak(bytes(attempt.raw_transaction))), attempt.tx_hash)
                self.assertEqual(Transaction.from_bytes(bytes(attempt.raw_transaction)).nonce, attempt.nonce)
                self.assertEqual(attempt.nonce, 7)
                self.assertEqual(SigningAccount.objects.get().next_nonce, 8)
            code, out, err = finish(worker(directory, "recover", database=self.database()))
            self.assertEqual(code, 0, out + err)
            ledger = json.loads((directory / "node.json").read_text())
            self.assertEqual(len(ledger["hashes"]), 1)
            self.assertEqual(len(set(ledger["broadcasts"])), 1)
            self.assertEqual(len(ledger["broadcasts"]), 2 if phase == "after_send" else 1)
            operation.refresh_from_db()
            self.assertEqual(operation.status, OutgoingStatus.CONFIRMED)
            self.assertEqual(operation.current_attempt.tx_hash, ledger["hashes"][0])
            self.assertEqual(SignedAttempt.objects.count(), 1)
            self.assertEqual(SigningAccount.objects.get().next_nonce, 8)

    def test_postgresql_kill_before_commit_rolls_back_the_signed_attempt_and_nonce(self):
        self.recover_postgresql_crash("before_commit")

    def test_postgresql_kill_after_commit_before_send_preserves_the_same_signed_attempt(self):
        self.recover_postgresql_crash("before_send")

    def test_postgresql_kill_after_node_acceptance_replays_only_the_committed_bytes(self):
        self.recover_postgresql_crash("after_send")
