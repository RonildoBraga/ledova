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
from uuid import uuid4

from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from web3 import Web3

from blockchain.models import (
    OutgoingCutoverHold,
    OutgoingHistoryCapture,
    OutgoingHistoryEvidence,
)
from blockchain.services.outgoing_inventory import collect_inventory, record_inventory
from blockchain.tests.outgoing_inventory_fixtures import (
    CONTRACT,
    RECIPIENT,
    signed_source,
)
from blockchain.tests.test_outgoing_processes import finish
from shared.db import atomic
from shared.tests.tenants import make_tenant
from tokens.models import ShareIssuance, ShareIssuanceRequest, ShareToken


def worker(directory, phase, index=0, database=None):
    env = os.environ.copy()
    if database:
        env["INVENTORY_TEST_DATABASE"] = json.dumps(database)
    return subprocess.Popen(
        [sys.executable, "-m", "blockchain.tests.outgoing_inventory_worker", str(directory), phase, str(index)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class OutgoingInventoryCrashTest(SimpleTestCase):
    def test_killed_import_rolls_back_partial_capture_evidence_and_holds(self):
        with tempfile.TemporaryDirectory(prefix="inventory-crash-") as temporary:
            directory = Path(temporary)
            code, out, err = finish(worker(directory, "kill"))
            self.assertEqual(code, -signal.SIGKILL, out + err)
            with sqlite3.connect(directory / "inventory.sqlite3") as independent:
                for table in (
                    "blockchain_outgoinghistorycapture",
                    "blockchain_outgoinghistoryevidence",
                    "blockchain_outgoingcutoverhold",
                ):
                    self.assertEqual(independent.execute(f"SELECT count(*) FROM {table}").fetchone(), (0,))
            code, out, err = finish(worker(directory, "recover"))
            self.assertEqual(code, 0, out + err)
            self.assertEqual(json.loads(out)["evidence_count"], 1)
            code, out, err = finish(worker(directory, "recover"))
            self.assertEqual(code, 0, out + err)
            with sqlite3.connect(directory / "inventory.sqlite3") as independent:
                self.assertEqual(
                    independent.execute("SELECT count(*) FROM blockchain_outgoinghistorycapture").fetchone(), (1,)
                )
                self.assertEqual(
                    independent.execute("SELECT count(*) FROM blockchain_outgoinghistoryevidence").fetchone(), (1,)
                )
                raw, tx_hash = independent.execute(
                    "SELECT raw_transaction, observed_hash FROM blockchain_outgoinghistoryevidence"
                ).fetchone()
                self.assertEqual(Web3.to_hex(Web3.keccak(raw)), tx_hash)
                self.assertGreater(
                    independent.execute("SELECT count(*) FROM blockchain_outgoingcutoverhold").fetchone()[0], 0
                )


@skipUnless(
    connection.vendor == "postgresql", "Independent capture serialization and snapshot checks require PostgreSQL"
)
class OutgoingInventoryProcessTest(TransactionTestCase):
    def database(self):
        fields = ("ENGINE", "NAME", "USER", "PASSWORD", "HOST", "PORT", "OPTIONS")
        return {key: connection.settings_dict[key] for key in fields}

    def wait_for_files(self, directory, pattern, count):
        until = time.monotonic() + 20
        while len(list(directory.glob(pattern))) < count and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(len(list(directory.glob(pattern))), count)

    def test_independent_postgresql_captures_cannot_miss_a_cross_capture_nonce_conflict(self):
        with tempfile.TemporaryDirectory(prefix="inventory-race-") as temporary:
            directory = Path(temporary)
            processes = [worker(directory, "race", index, self.database()) for index in range(2)]
            try:
                self.wait_for_files(directory, "ready-*", 2)
                (directory / "go").touch()
                self.wait_for_files(directory, "analyzing-*", 1)
                time.sleep(0.2)
                self.assertEqual(len(list(directory.glob("analyzing-*"))), 1)
                (directory / "analyze").touch()
                for process in processes:
                    code, out, err = finish(process)
                    self.assertEqual(code, 0, out + err)
                self.assertEqual(OutgoingHistoryCapture.objects.count(), 2)
                self.assertEqual(OutgoingHistoryEvidence.objects.count(), 2)
                self.assertEqual(OutgoingHistoryEvidence.objects.values("observed_hash").distinct().count(), 2)
                hold = OutgoingCutoverHold.objects.get(reason="nonce_payload_conflict")
                self.assertEqual(len(hold.evidence_refs), 2)
                self.assertEqual(
                    {ref["fingerprint"] for ref in hold.evidence_refs},
                    set(OutgoingHistoryEvidence.objects.values_list("source_fingerprint", flat=True)),
                )
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_postgresql_killed_import_has_no_partial_batch_and_reentry_commits_once(self):
        with tempfile.TemporaryDirectory(prefix="inventory-pg-crash-") as temporary:
            directory = Path(temporary)
            code, out, err = finish(worker(directory, "kill", database=self.database()))
            self.assertEqual(code, -signal.SIGKILL, out + err)
            self.assertFalse(OutgoingHistoryCapture.objects.exists())
            self.assertFalse(OutgoingHistoryEvidence.objects.exists())
            self.assertFalse(OutgoingCutoverHold.objects.exists())
            for _ in range(2):
                code, out, err = finish(worker(directory, "recover", database=self.database()))
                self.assertEqual(code, 0, out + err)
            self.assertEqual(OutgoingHistoryCapture.objects.count(), 1)
            self.assertEqual(OutgoingHistoryEvidence.objects.count(), 1)
            self.assertGreater(OutgoingCutoverHold.objects.count(), 0)

    def test_postgresql_capture_keeps_one_source_snapshot_while_a_legacy_writer_advances(self):
        tenant = make_tenant("inventory-snapshot")
        ShareToken.objects.filter(pk=tenant.deployed_token.pk).update(contract_address=CONTRACT)
        request = ShareIssuanceRequest.objects.create(
            token=tenant.deployed_token,
            recipient_address=RECIPIENT,
            amount=10,
            reason="Synthetic snapshot",
            status="failed",
        )
        entry = signed_source()["journal_entry"]
        issuance = ShareIssuance.objects.create(
            token=tenant.deployed_token,
            recipient_address=RECIPIENT,
            amount="10",
            status="failed",
            tx_hash=entry["tx_hash"],
            mint_journal=[entry],
            idempotency_key=f"issuance-request:{request.pk}",
        )
        with tempfile.TemporaryDirectory(prefix="inventory-snapshot-") as temporary:
            directory = Path(temporary)
            process = worker(directory, "snapshot", database=self.database())
            try:
                self.wait_for_files(directory, "snapshot-started", 1)
                with atomic():
                    ShareToken.objects.filter(pk=tenant.deployed_token.pk).update(contract_address=RECIPIENT)
                    ShareIssuance.objects.filter(pk=issuance.pk).update(amount="11")
                    ShareIssuanceRequest.objects.filter(pk=request.pk).update(amount=11)
                (directory / "writer-finished").touch()
                code, out, err = finish(process)
                self.assertEqual(code, 0, out + err)
                self.assertFalse(json.loads(out)["cutover_authorized"])
                first = OutgoingHistoryEvidence.objects.get(source_uuid=issuance.pk)
                self.assertEqual(first.expected_terms["to"], CONTRACT)
                self.assertEqual(first.expected_terms["amount"], "10")
                self.assertTrue(first.terms_match and first.source_link_valid)
                second = record_inventory(collect_inventory(), uuid4())
                self.assertFalse(second["cutover_authorized"])
                latest = OutgoingHistoryEvidence.objects.filter(source_uuid=issuance.pk).order_by("created_at").last()
                self.assertEqual(latest.expected_terms["to"], RECIPIENT)
                self.assertEqual(latest.expected_terms["amount"], "11")
                self.assertFalse(latest.terms_match)
                self.assertTrue(OutgoingCutoverHold.objects.filter(reason="source_identity_conflict").exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
