import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.conf import settings
from django.db import DatabaseError, connections, transaction
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
from wallets.models import Transaction, WalletChainObservation, WalletChainWatch
from wallets.services.chain_observations import (
    claim_chain_observation,
    complete_chain_observation,
    observe_wallet_chain,
)
from wallets.tasks.chain_observations import observe_wallet_chains
from wallets.tests.test_submission_durability import SubmissionFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"
BLOCK_HASH = "0x" + "22" * 32
HEAD_HASH = "0x" + "44" * 32


class ChainObservationFixture(SubmissionFixture):
    def setUp(self):
        super().setUp()
        self.signed_transfer = self.signed()
        with patch(
            "wallets.services.submissions.get_blockchain_client", return_value=self.provider(self.signed_transfer)
        ):
            self.submit_direct(self.signed_transfer)
        self.tx_id = self.submission().transaction_id
        self.observer = Mock(spec=["assert_expected_chain", "get_transaction_receipt", "w3"])
        self.observer.assert_expected_chain.return_value = settings.BLOCKCHAIN_CHAIN_ID
        self.observer.get_transaction_receipt.return_value = {
            "transactionHash": self.signed_transfer.hash.to_0x_hex(),
            "blockHash": BLOCK_HASH,
            "blockNumber": 100,
            "status": 1,
            "gasUsed": 21000,
            "effectiveGasPrice": 2000000000,
        }
        self.block = {"hash": BLOCK_HASH, "number": 100, "timestamp": 1700000000}
        self.head = {"hash": HEAD_HASH, "number": 104, "timestamp": 1700000000}
        self.observer.w3.eth.get_block.side_effect = lambda identifier: (
            self.head if identifier == "latest" else self.block
        )
        boundary = patch("wallets.services.chain_observations.get_blockchain_client", return_value=self.observer)
        boundary.start()
        self.addCleanup(boundary.stop)

    def observations(self):
        with use_operator():
            return list(WalletChainObservation.objects.order_by("generation").values())

    def watch(self):
        with use_operator():
            return WalletChainWatch.objects.get(transaction_id=self.tx_id)

    def assert_database_refuses(self, sql, params):
        with atomic():
            try:
                with self.assertRaises(DatabaseError), connections[current_alias()].cursor() as cursor:
                    cursor.execute(sql, params)
            finally:
                transaction.set_rollback(True, using=current_alias())


class ChainObservationChecks(ChainObservationFixture):
    def test_nonce_evidence_uses_the_immutable_signed_journal_without_financial_effects(self):
        self.observer.get_transaction_receipt.return_value = None
        candidate = {
            "result": "candidate",
            "reason": "",
            "candidate": {"tx_hash": "0x" + "55" * 32},
            "evidence": {"complete": True, "head": {"hash": HEAD_HASH, "height": 104}},
        }
        before = self.financial_state()
        with patch("wallets.services.chain_observations.collect_nonce_evidence", return_value=candidate) as read:
            self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
            read.assert_called_once_with(
                self.observer,
                bytes(self.signed_transfer.raw_transaction),
                admission=self.submission().intent["mined_nonce_observation"],
            )
        self.assertEqual(self.observations()[0]["evidence"]["nonce_spend"], candidate)
        self.assertEqual(self.financial_state(), before)

    def test_nonce_evidence_from_a_different_head_remains_unknown(self):
        self.observer.get_transaction_receipt.return_value = None
        candidate = {
            "result": "candidate",
            "reason": "",
            "candidate": {"tx_hash": "0x" + "55" * 32},
            "evidence": {"complete": True, "head": {"hash": "0x" + "66" * 32, "height": 104}},
        }
        before = self.financial_state()
        with patch("wallets.services.chain_observations.collect_nonce_evidence", return_value=candidate):
            self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        nonce = self.observations()[0]["evidence"]["nonce_spend"]
        self.assertEqual((nonce["result"], nonce["reason"]), ("unknown", "observation_head_changed"))
        self.assertFalse(nonce["evidence"]["complete"])
        self.assertNotIn("candidate", nonce)
        self.assertEqual(self.financial_state(), before)

    def test_wallet_state_changed_during_nonce_search_discards_the_observation(self):
        self.observer.get_transaction_receipt.return_value = None

        def change_state(address, height):
            with use_operator():
                Transaction.objects.filter(pk=self.tx_id).update(status="failed")
            return 0

        self.observer.w3.eth.get_transaction_count.side_effect = change_state
        self.assertEqual(observe_wallet_chain(self.tx_id), "observation_changed")
        self.assertEqual(self.observations(), [])

    def test_finality_provider_failure_retains_inclusion_without_financial_effects(self):
        network = f"evm:{settings.BLOCKCHAIN_CHAIN_ID}"
        before = self.financial_state()

        def unavailable_finality(identifier):
            if identifier == "finalized":
                raise ConnectionError("Synthetic unsupported finalized tag")
            return self.head if identifier == "latest" else self.block

        self.observer.w3.eth.get_block.side_effect = unavailable_finality
        with override_settings(WALLET_CHAIN_FINALITY_POLICIES={network: {"mode": "finalized"}}):
            self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        row = self.observations()[0]
        self.assertEqual(
            (row["result"], row["finality"], row["reason"]), ("included", "unknown", "finality_unavailable")
        )
        self.assertEqual(self.financial_state(), before)

    def test_conflicting_inclusion_remains_unknown_and_keeps_the_last_validated_context(self):
        network = f"evm:{settings.BLOCKCHAIN_CHAIN_ID}"
        before = self.financial_state()
        with override_settings(WALLET_CHAIN_FINALITY_POLICIES={network: {"mode": "depth", "depth": 1}}):
            self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
            first = self.observations()[0]
            self.assertEqual(first["finality"], "satisfied")
            changed_hash = "0x" + "33" * 32
            changed = {**self.block, "number": 101, "hash": changed_hash}
            self.observer.get_transaction_receipt.return_value.update(blockHash=changed_hash, blockNumber=101)
            self.observer.w3.eth.get_block.side_effect = lambda identifier: (
                self.head if identifier == "latest" else changed if identifier in (101, changed_hash) else self.block
            )
            self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        rows = self.observations()
        self.assertEqual(rows[0], first)
        self.assertEqual((rows[1]["result"], rows[1]["finality"]), ("unknown", "unknown"))
        self.assertEqual(rows[1]["reason"], "previous_inclusion_still_canonical")
        self.assertEqual(claim_chain_observation(self.tx_id).previous_block["hash"], BLOCK_HASH)
        self.assertEqual(self.financial_state(), before)

    def test_successive_reads_keep_inclusion_then_unknown_without_financial_effects(self):
        before = self.financial_state()
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        first = self.observations()[0]
        self.assertEqual((first["result"], first["finality"]), ("included", "unknown"))
        self.assertEqual(first["policy"], {"version": 1, "mode": "unconfigured"})
        self.observer.get_transaction_receipt.return_value = None
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        rows = self.observations()
        self.assertEqual(rows[0], first)
        self.assertEqual((rows[1]["generation"], rows[1]["result"]), (2, "unknown"))
        self.assertEqual(rows[1]["evidence"]["previous_block"], {"hash": BLOCK_HASH, "height": 100})
        self.assertEqual(self.watch().latest_observation_id, rows[1]["uuid"])
        self.assertEqual(self.financial_state(), before)

    def test_a_late_result_cannot_overwrite_a_newer_claim_and_repeated_completion_is_idempotent(self):
        older = claim_chain_observation(self.tx_id)
        newer = claim_chain_observation(self.tx_id)
        result = {"result": "unknown", "finality": "unknown", "reason": "receipt_unavailable", "evidence": {}}
        self.assertEqual(complete_chain_observation(newer, result), "recorded")
        before = self.observations()
        self.assertEqual(complete_chain_observation(older, result), "observation_changed")
        self.assertEqual(complete_chain_observation(newer, result), "already_recorded")
        self.assertEqual(self.observations(), before)
        self.assertEqual(before[0]["generation"], 2)

    def test_a_target_change_during_rpc_invalidates_the_complete_receipt_observation(self):
        original = dict(self.observer.get_transaction_receipt.return_value)

        def changed(tx_hash):
            with use_operator():
                Transaction.objects.filter(pk=self.tx_id).update(status="failed")
            return original

        self.observer.get_transaction_receipt.side_effect = changed
        self.assertEqual(observe_wallet_chain(self.tx_id), "observation_changed")
        self.assertEqual(self.observations(), [])
        self.assertIsNone(self.watch().latest_observation_id)
        self.observer.get_transaction_receipt.side_effect = None
        before = self.financial_state()
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        self.assertEqual(self.financial_state(), before)

    def test_finality_is_an_explicit_policy_snapshot_and_does_not_settle_a_wallet(self):
        network = f"evm:{settings.BLOCKCHAIN_CHAIN_ID}"
        before = self.financial_state()
        for policy, expected in (
            ({"mode": "depth", "depth": 6}, "waiting"),
            ({"mode": "depth", "depth": 5}, "satisfied"),
            ({"mode": "depth", "depth": True}, "unknown"),
        ):
            with self.subTest(policy=policy), override_settings(WALLET_CHAIN_FINALITY_POLICIES={network: policy}):
                self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
                self.assertEqual(self.observations()[-1]["finality"], expected)
        self.assertEqual(self.financial_state(), before)

    def test_rpc_runs_after_a_durable_claim_and_outside_a_database_transaction(self):
        original = dict(self.observer.get_transaction_receipt.return_value)
        observed = []

        def inspect(tx_hash):
            with use_operator():
                observed.append(
                    (connections[current_alias()].in_atomic_block, self.watch().generation, self.observations())
                )
            return original

        self.observer.get_transaction_receipt.side_effect = inspect
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        self.assertEqual(observed, [(False, 1, [])])

    def test_a_missing_provider_still_records_unknown_and_an_abandoned_claim_can_resume(self):
        first = claim_chain_observation(self.tx_id)
        with patch(
            "wallets.services.chain_observations.get_blockchain_client", side_effect=TimeoutError("Synthetic outage")
        ):
            self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        rows = self.observations()
        self.assertEqual(
            (rows[0]["generation"], rows[0]["result"], rows[0]["reason"]),
            (first.generation + 1, "unknown", "provider_unavailable"),
        )

    def test_the_periodic_observer_includes_terminal_rows_and_defers_recently_started_reads(self):
        with use_operator():
            Transaction.objects.filter(pk=self.tx_id).update(status="confirmed")
        before = self.financial_state()
        self.assertEqual(observe_wallet_chains(0), {"attempted": 1, "outcomes": {"recorded": 1}})
        self.assertEqual(observe_wallet_chains(0), {"attempted": 0, "outcomes": {}})
        later = timezone.now() + timedelta(minutes=3)
        with patch("wallets.tasks.chain_observations.timezone.now", return_value=later):
            self.assertEqual(observe_wallet_chains(0), {"attempted": 1, "outcomes": {"recorded": 1}})
        self.assertEqual(len(self.observations()), 2)
        after = self.financial_state()
        self.assertEqual(after[1:], before[1:])
        with use_operator():
            tx = Transaction.objects.get(pk=self.tx_id)
            self.assertIsNotNone(tx.balance_reconciliation_token)
            self.assertEqual(tx.block_hash, BLOCK_HASH)

    @skipUnless(POSTGRES, "Database guards require PostgreSQL")
    def test_postgres_keeps_the_watch_identity_and_observations_immutable(self):
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        watch = self.watch()
        row = self.observations()[0]
        with use_operator():
            for sql, params in (
                ("UPDATE wallets_walletchainwatch SET tx_hash = %s WHERE uuid = %s", ["0x" + "33" * 32, watch.pk]),
                ("UPDATE wallets_walletchainwatch SET generation = generation + 2 WHERE uuid = %s", [watch.pk]),
                ("UPDATE wallets_walletchainwatch SET target_fingerprint = %s WHERE uuid = %s", ["33" * 32, watch.pk]),
                ("DELETE FROM wallets_walletchainwatch WHERE uuid = %s", [watch.pk]),
                ("UPDATE wallets_walletchainobservation SET evidence = '{}' WHERE uuid = %s", [row["uuid"]]),
                ("DELETE FROM wallets_walletchainobservation WHERE uuid = %s", [row["uuid"]]),
            ):
                with self.subTest(sql=sql):
                    self.assert_database_refuses(sql, params)
        self.assertEqual(self.observations(), [row])

    @skipUnless(POSTGRES, "Concurrent durable claims require PostgreSQL")
    def test_concurrent_claims_use_distinct_generations_and_only_the_latest_can_finish(self):
        gate = Barrier(2)

        def claim():
            try:
                gate.wait(timeout=10)
                return claim_chain_observation(self.tx_id)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(claim) for _ in range(2)]
            claims = sorted((item.result(timeout=15) for item in pending), key=lambda item: item.generation)
        self.assertEqual([item.generation for item in claims], [1, 2])
        result = {"result": "unknown", "finality": "unknown", "reason": "receipt_unavailable", "evidence": {}}
        self.assertEqual(complete_chain_observation(claims[0], result), "observation_changed")
        self.assertEqual(complete_chain_observation(claims[1], result), "recorded")
        self.assertEqual(len(self.observations()), 1)

    @skipUnless(POSTGRES, "Database observation links require PostgreSQL")
    def test_postgres_refuses_foreign_accounts_and_stale_generations_at_insert(self):
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        older = claim_chain_observation(self.tx_id)
        current = claim_chain_observation(self.tx_id)
        with use_operator():
            other = make_tenant("observation-forged")
            with atomic():
                for account, claim in ((other.account.pk, current), (self.tenant.account.pk, older)):
                    with self.subTest(account=account, generation=claim.generation), atomic():
                        try:
                            with self.assertRaises(DatabaseError):
                                WalletChainObservation.objects.create(
                                    watch_id=current.watch_id,
                                    user_account_id=account,
                                    generation=claim.generation,
                                    target_fingerprint=claim.target_fingerprint,
                                    started_at=claim.started_at,
                                    result="unknown",
                                    finality="unknown",
                                    reason="receipt_unavailable",
                                )
                        finally:
                            transaction.set_rollback(True, using=current_alias())
        result = {"result": "unknown", "finality": "unknown", "reason": "receipt_unavailable", "evidence": {}}
        self.assertEqual(complete_chain_observation(current, result), "recorded")
        self.assertEqual([row["generation"] for row in self.observations()], [1, 3])

    @skipUnless(POSTGRES, "Database journal binding requires PostgreSQL")
    def test_a_watch_cannot_invent_a_network_owner_or_legacy_journal(self):
        with use_operator():
            other = make_tenant("observation-journal-binding")
            unrecorded = Transaction.objects.create(
                wallet=self.wallet,
                user_account=self.tenant.account,
                asset=self.native,
                chain=self.wallet.chain,
                tx_hash="0x" + "77" * 32,
                amount=0,
                from_address=self.wallet.address,
                to_address=self.recipient,
                status="pending",
            )
            for tx_id, account, network, tx_hash in (
                (self.tx_id, self.tenant.account.pk, "evm:1", self.signed_transfer.hash.to_0x_hex()),
                (
                    self.tx_id,
                    other.account.pk,
                    f"evm:{settings.BLOCKCHAIN_CHAIN_ID}",
                    self.signed_transfer.hash.to_0x_hex(),
                ),
                (unrecorded.pk, self.tenant.account.pk, f"evm:{settings.BLOCKCHAIN_CHAIN_ID}", unrecorded.tx_hash),
            ):
                with self.subTest(network=network, account=account, tx_id=tx_id), atomic():
                    try:
                        with self.assertRaises(DatabaseError):
                            WalletChainWatch.objects.create(
                                transaction_id=tx_id,
                                wallet=self.wallet,
                                user_account_id=account,
                                chain=self.wallet.chain,
                                network=network,
                                tx_hash=tx_hash,
                            )
                    finally:
                        transaction.set_rollback(True, using=current_alias())
        self.assertIsNone(claim_chain_observation(unrecorded.pk))
        self.assertEqual(claim_chain_observation(self.tx_id).generation, 1)

    @skipUnless(POSTGRES and hasattr(os, "fork"), "Durable process recovery requires PostgreSQL and fork")
    def test_process_exit_after_a_claim_keeps_it_and_a_new_reader_recovers(self):
        connections.close_all()
        child = os.fork()
        if child == 0:
            try:
                claim_chain_observation(self.tx_id)
                os._exit(23)
            finally:
                os._exit(24)
        exited = False
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                reaped, status = os.waitpid(child, os.WNOHANG)
                if reaped:
                    exited = True
                    self.assertEqual(os.waitstatus_to_exitcode(status), 23)
                    break
                time.sleep(0.01)
            self.assertTrue(exited)
        finally:
            if not exited:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
        self.assertEqual(self.watch().generation, 1)
        self.assertEqual(self.observations(), [])
        before = self.financial_state()
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        self.assertEqual(self.observations()[0]["generation"], 2)
        self.assertEqual(self.financial_state(), before)

    def test_bounded_batches_eventually_read_every_previously_unobserved_journal(self):
        for nonce in range(10, 35):
            signed = self.signed(nonce=nonce, value=0)
            with patch("wallets.services.submissions.get_blockchain_client", return_value=self.provider(signed)):
                self.submit_direct(signed)
        first = observe_wallet_chains(0)
        second = observe_wallet_chains(0)
        self.assertEqual((first["attempted"], second["attempted"]), (25, 1))
        with use_operator():
            self.assertEqual(WalletChainWatch.objects.count(), 26)
            self.assertEqual(WalletChainObservation.objects.count(), 26)
        self.assertEqual(observe_wallet_chains(0)["attempted"], 0)


class ChainObservationTest(ChainObservationChecks, APITransactionTestCase):
    pass


class ScopedChainObservationTest(RunsOnTheScopedConnection, ChainObservationChecks, APITransactionTestCase):
    def test_only_the_owner_reads_the_observations_and_even_the_owner_cannot_write_them(self):
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        watch = self.watch()
        row = self.observations()[0]
        with use_operator():
            other = make_tenant("observation-private")
        with acting_for(other.user.pk):
            self.assertEqual(WalletChainWatch.objects.count(), 0)
            self.assertEqual(WalletChainObservation.objects.count(), 0)
        with acting_for(self.tenant.user.pk):
            self.assertEqual(WalletChainWatch.objects.get().pk, watch.pk)
            self.assertEqual(WalletChainObservation.objects.get().pk, row["uuid"])
            self.assert_database_refuses(
                "UPDATE wallets_walletchainwatch SET generation = generation + 1, "
                "last_started_at = CURRENT_TIMESTAMP WHERE uuid = %s",
                [watch.pk],
            )
