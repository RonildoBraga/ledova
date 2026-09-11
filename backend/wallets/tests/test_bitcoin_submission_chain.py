import os
import signal
import time
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import requests
from django.db import connection, connections
from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from assets.services.identity import native_asset_for_chain
from integrations.blockchain.bitcoin import BitcoinClient
from shared.db import acting_for, use_operator
from shared.tests.tenants import make_tenant
from wallets.models import (
    BitcoinSubmission,
    BitcoinSubmissionInput,
    Holding,
    Transaction,
    Wallet,
)
from wallets.services import transfers
from wallets.services.bitcoin_submissions import attempt_bitcoin_submission
from wallets.tasks.confirmation import confirm_pending_transaction

RPC_URL = os.environ.get("BITCOIN_TEST_RPC_URL", "")
COOKIE = os.environ.get("BITCOIN_TEST_COOKIE", "")


@skipUnless(
    RPC_URL and COOKIE and connection.vendor == "postgresql",
    "An isolated Bitcoin regtest and PostgreSQL are required",
)
@override_settings(BITCOIN_NETWORK="regtest")
class BitcoinSubmissionChainTest(APITransactionTestCase):
    def setUp(self):
        super().setUp()
        url = urlsplit(RPC_URL)
        self.assertEqual((url.scheme, url.hostname), ("http", "127.0.0.1"))
        self.provider = object.__new__(BitcoinClient)
        self.provider.rpc_url = RPC_URL
        self.provider.expected_network = "regtest"
        self.provider.session = requests.Session()
        self.provider.session.auth = tuple(Path(COOKIE).read_text().strip().split(":", 1))
        self.addCleanup(self.provider.session.close)
        self.assertEqual(self.provider.assert_expected_network(), "regtest")
        network = self.provider._rpc_call("getnetworkinfo")
        self.assertFalse(network["networkactive"])
        self.assertEqual(network["connections"], 0)
        name = f"ledova-{uuid4()}"
        self.provider._rpc_call("createwallet", [name])
        self.addCleanup(self.provider._rpc_call, "unloadwallet", [name])
        self.provider.rpc_url = f"{RPC_URL}/wallet/{name}"
        self.sender = self.provider._rpc_call("getnewaddress", ["sender", "bech32"])
        self.recipient = self.provider._rpc_call("getnewaddress", ["recipient", "bech32"])
        self.miner = self.provider._rpc_call("getnewaddress", ["miner", "bech32"])
        self.provider._rpc_call("generatetoaddress", [1, self.sender])
        self.provider._rpc_call("generatetoaddress", [100, self.miner])
        previous = self.provider._rpc_call("listunspent", [101, 9999999, [self.sender]])[0]
        self.starting_amount = previous["amount"]
        self.assertGreater(self.starting_amount, Decimal("4.0002"))
        raw = self.provider._rpc_call(
            "createrawtransaction",
            [
                [{"txid": previous["txid"], "vout": previous["vout"]}],
                [{self.recipient: "2"}, {self.sender: str(self.starting_amount - Decimal("2.0001"))}],
            ],
        )
        signed = self.provider._rpc_call("signrawtransactionwithwallet", [raw])
        self.assertTrue(signed["complete"])
        self.raw = signed["hex"]
        self.decoded = self.provider._rpc_call("decoderawtransaction", [self.raw])
        with use_operator():
            self.tenant = make_tenant("bitcoin-real-chain")
            self.wallet = Wallet.objects.create(
                user_account=self.tenant.account,
                chain="bitcoin",
                address=self.sender,
                verification_status="VERIFIED",
            )
            self.asset = native_asset_for_chain("bitcoin")
            self.holding = Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=self.starting_amount)
        self.client.force_authenticate(self.tenant.user)
        for target in (
            "wallets.tasks.confirm_pending_transaction.configure",
            "wallets.services.transaction_confirmation.TransactionMonitoringService.check_new_transaction",
            "wallets.services.transaction_confirmation.send_transaction_notification.defer",
            "wallets.services.transaction_confirmation.sync_holding",
        ):
            boundary = patch(target)
            boundary.start()
            self.addCleanup(boundary.stop)
        provider = patch(
            "integrations.blockchain.factory.BlockchainClientFactory.get_client",
            return_value=self.provider,
        )
        provider.start()
        self.addCleanup(provider.stop)

    def submit_direct(self):
        with acting_for(self.tenant.user.pk):
            return transfers.broadcast_transfer(self.wallet, self.raw, principal_id=self.tenant.user.pk)

    def submission(self):
        with use_operator():
            return BitcoinSubmission.objects.get(wallet=self.wallet)

    def financial_state(self):
        with use_operator():
            return list(Transaction.objects.filter(wallet=self.wallet).values()), list(
                Holding.objects.filter(wallet=self.wallet).values()
            )

    def mine_and_confirm(self):
        submission = self.submission()
        block_hash = self.provider._rpc_call("generatetoaddress", [1, self.miner])[0]
        block = self.provider._rpc_call("getblock", [block_hash, 2])
        mined = next(tx for tx in block["tx"] if tx["txid"] == submission.tx_hash)
        self.assertEqual(mined["hash"], submission.witness_hash)
        self.assertEqual(
            self.provider._rpc_call("gettxout", [mined["txid"], 0])["value"],
            Decimal("2"),
        )
        self.assertEqual(
            confirm_pending_transaction(
                submission.tx_hash,
                str(self.wallet.pk),
                principal_id=self.tenant.user.pk,
            )["status"],
            "confirmed",
        )
        with use_operator():
            tx = Transaction.objects.get(pk=submission.transaction_id)
            self.holding.refresh_from_db()
        self.assertEqual(tx.block_hash, block_hash)
        self.assertEqual(int(tx.block_timestamp.timestamp()), block["time"])
        self.assertEqual((tx.amount, tx.transaction_fee_estimated), (Decimal("2"), Decimal("0.0001")))
        self.assertEqual(self.holding.quantity, self.starting_amount - Decimal("2.0001"))
        before = self.financial_state()
        self.assertEqual(
            confirm_pending_transaction(
                submission.tx_hash,
                str(self.wallet.pk),
                principal_id=self.tenant.user.pk,
            )["status"],
            "already_processed",
        )
        self.assertEqual(self.financial_state(), before)

    def test_a_real_mempool_transaction_recovers_a_lost_response_and_confirms_once(
        self,
    ):
        send = self.provider.broadcast_transaction

        def lost_acknowledgement(raw):
            self.assertEqual(bytes(self.submission().raw_transaction).hex(), raw)
            self.assertEqual(send(raw), self.decoded["txid"])
            raise TimeoutError("Synthetic response loss after actual regtest acceptance")

        with patch.object(self.provider, "broadcast_transaction", side_effect=lost_acknowledgement):
            response = self.client.post(
                f"/api/wallets/{self.wallet.pk}/broadcast-transfer/",
                {"signed_transaction": self.raw},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], self.decoded["txid"])
        submission = self.submission()
        self.assertIsNone(submission.acknowledged_at)
        entry = self.provider._rpc_call("getmempoolentry", [submission.tx_hash])
        self.assertEqual(entry["wtxid"], self.decoded["hash"])
        self.assertEqual(entry["fees"]["base"], Decimal("0.0001"))
        before = self.financial_state()
        with use_operator(), patch.object(self.provider, "broadcast_transaction", wraps=send) as resent:
            self.assertEqual(attempt_bitcoin_submission(submission.pk), "acknowledged")
            resent.assert_not_called()
        self.assertEqual(self.financial_state(), before)
        self.mine_and_confirm()

    def test_node_validation_refuses_a_corrupted_signature_before_recording_or_sending(
        self,
    ):
        changed = bytearray.fromhex(self.raw)
        changed[-10] ^= 1
        response = self.client.post(
            f"/api/wallets/{self.wallet.pk}/broadcast-transfer/",
            {"signed_transaction": changed.hex()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.provider._rpc_call("getrawmempool"), [])
        with use_operator():
            self.assertEqual(BitcoinSubmission.objects.count(), 0)
            self.assertEqual(BitcoinSubmissionInput.objects.count(), 0)
            self.assertEqual(Transaction.objects.filter(wallet=self.wallet).count(), 0)
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, self.starting_amount)

    def test_process_exit_before_or_after_actual_send_keeps_recoverable_durable_intent(
        self,
    ):
        for phase in ("before_send", "after_send"):
            with self.subTest(phase=phase):
                if phase == "after_send":
                    changed = self.provider._rpc_call(
                        "createrawtransaction",
                        [
                            [{"txid": self.decoded["txid"], "vout": 1}],
                            [{self.recipient: "2"}, {self.sender: str(self.starting_amount - Decimal("4.0002"))}],
                        ],
                    )
                    self.raw = self.provider._rpc_call("signrawtransactionwithwallet", [changed])["hex"]
                    self.decoded = self.provider._rpc_call("decoderawtransaction", [self.raw])
                send = self.provider.broadcast_transaction
                connections.close_all()
                child = os.fork()
                if child == 0:
                    try:

                        def interrupted(raw):
                            if phase == "after_send":
                                send(raw)
                            os._exit(23)

                        with patch.object(
                            self.provider,
                            "broadcast_transaction",
                            side_effect=interrupted,
                        ):
                            self.submit_direct()
                    finally:
                        os._exit(24)
                exited = False
                try:
                    deadline = time.monotonic() + 20
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
                with use_operator():
                    submission = BitcoinSubmission.objects.get(wallet=self.wallet, tx_hash=self.decoded["txid"])
                self.assertEqual(bytes(submission.raw_transaction).hex(), self.raw)
                self.assertIsNone(submission.acknowledged_at)
                self.assertEqual(
                    self.provider._rpc_call("getrawmempool"),
                    [self.decoded["txid"]] if phase == "after_send" else [],
                )
                before = self.financial_state()
                with use_operator():
                    self.assertEqual(attempt_bitcoin_submission(submission.pk), "acknowledged")
                self.assertEqual(self.financial_state(), before)
                self.provider._rpc_call("generatetoaddress", [1, self.miner])
                self.assertEqual(
                    confirm_pending_transaction(
                        submission.tx_hash,
                        str(self.wallet.pk),
                        principal_id=self.tenant.user.pk,
                    )["status"],
                    "confirmed",
                )
        with use_operator():
            self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, self.starting_amount - Decimal("4.0002"))
