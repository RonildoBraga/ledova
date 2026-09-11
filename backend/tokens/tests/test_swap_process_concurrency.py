import json
import os
import select
import subprocess
import sys
import tempfile
import time
from unittest import skipUnless
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError, connection
from django.test import TransactionTestCase, override_settings
from eth_account.messages import encode_typed_data

from blockchain.models import BlockchainTransaction
from shared.db import atomic
from shared.tests.tenants import make_tenant
from tokens.models import SwapOrder, SwapOrderStatus, TransferOrder, TransferOrderType
from tokens.services.trading_locks import lock_orders
from tokens.services.trading_order_cancel import cancel_signed_order
from tokens.services.trading_order_service import TradingOrderService
from tokens.tests.swap_state_fixtures import (
    BUYER,
    CONFIRMED,
    CONTRACT,
    OTHER_HASH,
    REVERTED,
    SELLER,
    TX_HASH,
    attach_claim,
    make_swap,
    persisted_outcome,
    swap_service,
    transaction_for,
)
from wallets.models import Wallet


class SwapProcess:

    def __init__(self, test, mode, row_id, detail=""):
        self.test = test
        self.errors = tempfile.TemporaryFile()
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tokens.tests.swap_state_worker", mode, str(row_id), detail],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            bufsize=0,
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "ledova_backend.settings.test_postgres",
                "TRADING_TEST_DATABASE": json.dumps(connection.settings_dict, default=str),
                "TRADING_TEST_CHAIN_ID": str(settings.BLOCKCHAIN_CHAIN_ID),
            },
        )
        test.addCleanup(self.close)
        loaded = self.receive("loaded")
        test.assertNotEqual(loaded["pid"], os.getpid())
        self.database_pid = loaded["database_pid"]

    def error_output(self):
        self.errors.seek(0)
        return self.errors.read().decode()[-5000:]

    def receive(self, stage):
        readable, _, _ = select.select([self.process.stdout], [], [], 25)
        self.test.assertTrue(readable, f"Worker did not reach {stage}: {self.error_output()}")
        line = self.process.stdout.readline()
        self.test.assertTrue(line, self.error_output())
        event = json.loads(line)
        self.test.assertEqual(event["stage"], stage, (event, self.error_output()))
        return event

    def send(self, command):
        self.process.stdin.write((command + "\n").encode())
        self.process.stdin.flush()

    def done(self):
        result = self.receive("done")
        self.test.assertEqual(self.process.wait(timeout=10), 0, self.error_output())
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()
        self.errors.close()


@skipUnless(connection.vendor == "postgresql", "Independent processes require PostgreSQL row locks")
@override_settings(ATOMIC_SWAP_ADDRESS=CONTRACT, BLOCKCHAIN_OPERATOR_KEY="0x" + "11" * 32)
class SwapWorkersUseOneCurrentClaimTest(TransactionTestCase):

    def setUp(self):
        self.swap = make_swap("process-swap", ready=True)
        for path in (
            "tokens.services.atomic_swap_service.publish_trading_event",
            "tokens.services.trading_order_cancel.publish_trading_event",
        ):
            publisher = patch(path)
            publisher.start()
            self.addCleanup(publisher.stop)

    def wait_for_row_lock(self, child, table, blocker_pid=None):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT query, COALESCE(%s, pg_backend_pid()) = ANY(pg_blocking_pids(pid)), wait_event_type "
                    "FROM pg_stat_activity WHERE pid = %s",
                    [blocker_pid, child.database_pid],
                )
                observed = cursor.fetchone()
            if (
                observed
                and observed[1]
                and observed[0].startswith("SELECT ")
                and table in observed[0]
                and observed[2] == "Lock"
            ):
                return
            time.sleep(0.01)
        self.fail(f"Worker never waited for the held {table} row: {observed}")

    def test_two_ready_workers_prepare_only_one_committed_claim(self):
        first = SwapProcess(self, "execute", self.swap.pk)
        second = SwapProcess(self, "execute", self.swap.pk)
        first.send("run")
        self.assertFalse(first.receive("prepare")["in_atomic"])
        self.swap.refresh_from_db()
        self.assertEqual(self.swap.status, SwapOrderStatus.EXECUTING)
        self.assertIsNotNone(self.swap.transaction_id)
        with atomic():
            self.assertEqual(SwapOrder.objects.select_for_update(nowait=True).get(pk=self.swap.pk).status, "executing")
        second.send("run")
        self.assertEqual(second.done().get("refused"), "SwapNotReadyException")
        first.send("prepare")
        self.assertFalse(first.receive("sign")["in_atomic"])
        self.assertFalse(first.receive("send")["in_atomic"])
        self.assertEqual(first.done()["result"], TX_HASH)
        self.assertEqual(BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).count(), 1)
        self.swap.refresh_from_db()
        self.assertEqual(self.swap.transaction.tx_hash, TX_HASH)
        self.assertEqual(self.swap.sell_order.filled_quantity, 30)

    def test_opposite_verified_signatures_recompute_ready_after_the_other_commits(self):
        SwapOrder.objects.filter(pk=self.swap.pk).update(status="created", seller_signature="", buyer_signature="")
        seller = SwapProcess(self, "signature", self.swap.pk, "seller")
        buyer = SwapProcess(self, "signature", self.swap.pk, "buyer")
        seller.send("run")
        buyer.send("run")
        self.assertTrue(seller.receive("verified")["valid"])
        self.assertTrue(buyer.receive("verified")["valid"])
        seller.send("store")
        seller.done()
        buyer.send("store")
        self.assertEqual(buyer.done()["result"], SwapOrderStatus.READY)
        self.swap.refresh_from_db()
        signable = encode_typed_data(full_message=swap_service().get_typed_data(self.swap))
        self.assertEqual(self.swap.seller_signature, SELLER.sign_message(signable).signature.hex())
        self.assertEqual(self.swap.buyer_signature, BUYER.sign_message(signable).signature.hex())

    def test_an_overlapping_ready_claim_waits_for_the_first_locked_decision(self):
        first = SwapProcess(self, "execute_overlap", self.swap.pk)
        second = SwapProcess(self, "execute", self.swap.pk)
        first.send("run")
        self.assertTrue(first.receive("claim_locked")["in_atomic"])
        second.send("run")
        self.wait_for_row_lock(second, "tokens_swaporder", first.database_pid)
        self.assertFalse(BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).exists())
        first.send("claim")
        self.assertFalse(first.receive("prepare")["in_atomic"])
        self.assertEqual(second.done().get("refused"), "SwapNotReadyException")
        first.send("prepare")
        first.receive("sign")
        first.receive("send")
        self.assertEqual(first.done()["result"], TX_HASH)
        self.assertEqual(BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).count(), 1)

    def test_an_overlapping_signature_waits_and_reads_the_committed_other_signature(self):
        SwapOrder.objects.filter(pk=self.swap.pk).update(status="created", seller_signature="", buyer_signature="")
        seller = SwapProcess(self, "signature_overlap", self.swap.pk, "seller")
        buyer = SwapProcess(self, "signature", self.swap.pk, "buyer")
        seller.send("run")
        buyer.send("run")
        seller.receive("verified")
        buyer.receive("verified")
        seller.send("store")
        self.assertTrue(seller.receive("signature_locked")["in_atomic"])
        buyer.send("store")
        self.wait_for_row_lock(buyer, "tokens_swaporder", seller.database_pid)
        seller.send("signature")
        self.assertEqual(seller.done()["result"], SwapOrderStatus.SELLER_SIGNED)
        self.assertEqual(buyer.done()["result"], SwapOrderStatus.READY)
        self.swap.refresh_from_db()
        self.assertTrue(self.swap.seller_signature)
        self.assertTrue(self.swap.buyer_signature)

    def start_observation(self, kind, outcome):
        child = SwapProcess(self, kind, self.swap.pk, outcome)
        child.send("run")
        self.assertFalse(child.receive("observed")["in_atomic"])
        return child

    def changed_identity(self, change):
        with atomic():
            lock_orders(TransferOrder.objects.filter(pk__in=[self.swap.sell_order_id, self.swap.buy_order_id]))
            swap = SwapOrder.objects.select_for_update().get(pk=self.swap.pk)
            transaction = BlockchainTransaction.objects.select_for_update().get(pk=swap.transaction_id)
            if change == "uuid":
                transaction.tx_hash = OTHER_HASH
                transaction.save(update_fields=["tx_hash"])
                newer = transaction_for(swap, TX_HASH)
                swap.transaction = newer
            else:
                transaction.tx_hash = OTHER_HASH
                transaction.save(update_fields=["tx_hash"])
                swap.tx_hash = OTHER_HASH
            swap.save(update_fields=["transaction", "tx_hash"])

    def test_stale_uuid_and_hash_observations_cannot_apply_success_or_failure(self):
        for kind in ("receipt", "reconcile"):
            for change in ("uuid", "hash"):
                for outcome in ("positive", "negative"):
                    with self.subTest(kind=kind, change=change, outcome=outcome):
                        BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).delete()
                        self.swap.refresh_from_db()
                        attach_claim(self.swap)
                        child = self.start_observation(kind, outcome)
                        self.changed_identity(change)
                        before = persisted_outcome(self.swap)
                        child.send("apply")
                        self.assertIsNone(child.done()["result"])
                        self.assertEqual(persisted_outcome(self.swap), before)

    def test_a_late_opposite_receipt_cannot_reverse_settlement_or_cancellation(self):
        for outcome, first_receipt in (("negative", CONFIRMED), ("positive", REVERTED)):
            with self.subTest(late=outcome):
                BlockchainTransaction.objects.filter(related_uuid=self.swap.pk).delete()
                self.swap.refresh_from_db()
                attach_claim(self.swap)
                TransferOrder.objects.filter(pk__in=[self.swap.sell_order_id, self.swap.buy_order_id]).update(
                    filled_quantity=30, status="pending_signature"
                )
                child = self.start_observation("receipt", outcome)
                swap_service()._record_receipt(self.swap, self.swap.transaction, TX_HASH, first_receipt)
                if first_receipt == REVERTED:
                    order = TransferOrder.objects.get(pk=self.swap.sell_order_id)
                    issued = TradingOrderService.get_order_cancel_message(order)
                    signature = SELLER.sign_message(
                        encode_typed_data(
                            domain_data=issued["domain"], message_types=issued["types"], message_data=issued["message"]
                        )
                    ).signature.hex()
                    cancel_signed_order(order, issued["digest"], signature)
                before = persisted_outcome(self.swap)
                child.send("apply")
                self.assertIsNone(child.done()["result"])
                self.assertEqual(persisted_outcome(self.swap), before)

    def test_receipt_waits_for_and_rereads_the_actual_transaction_row(self):
        transaction = attach_claim(self.swap)
        child = SwapProcess(self, "receipt_locked", self.swap.pk, "negative")
        with atomic():
            current = BlockchainTransaction.objects.select_for_update().get(pk=transaction.pk)
            current.mark_confirmed(12, OTHER_HASH, 12345)
            child.send("run")
            child.receive("applying")
            self.wait_for_row_lock(child, "blockchain_blockchaintransaction")
        before = persisted_outcome(self.swap)
        self.assertIsNone(child.done()["result"])
        self.assertEqual(persisted_outcome(self.swap), before)

    def test_order_locks_use_primary_key_order_while_selection_keeps_best_price(self):
        tenant = make_tenant("match-locks")
        template = TransferOrder.objects.filter(pk=tenant.order.pk).values().get()
        tenant.swap.delete()
        tenant.order.cancel()
        wallet = Wallet.objects.create(user_account=tenant.account, address=BUYER.address, chain="base")
        incoming = TransferOrder.objects.create(
            **{
                **template,
                "uuid": UUID(int=3),
                "order_type": TransferOrderType.BUY,
                "wallet_id": wallet.pk,
                "wallet_address": wallet.address,
                "price_per_share": "3.00",
            }
        )
        low = TransferOrder.objects.create(**{**template, "uuid": UUID(int=1), "price_per_share": "2.00"})
        best = TransferOrder.objects.create(**{**template, "uuid": UUID(int=2), "price_per_share": "1.00"})
        child = SwapProcess(self, "match", incoming.pk)
        with atomic():
            TransferOrder.objects.select_for_update().get(pk=low.pk)
            child.send("run")
            self.wait_for_row_lock(child, "tokens_transferorder")
            try:
                with atomic():
                    TransferOrder.objects.select_for_update(nowait=True).get(pk=best.pk)
            except DatabaseError as exc:
                self.fail(f"The waiter acquired the higher primary key before the blocked lower key: {exc}")
        self.assertEqual(child.done()["result"], str(best.pk))
