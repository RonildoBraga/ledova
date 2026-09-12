import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from django.apps import apps
from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from assets.services.identity import native_asset_for_chain
from integrations.blockchain.bitcoin import BitcoinClient
from shared.db import acting_for, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.models import BitcoinSubmission, Holding, Transaction, Wallet
from wallets.services import transfers

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "bitcoin_submission.json").read_text())
REGTEST_GENESIS = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"


class BitcoinSubmissionFixture:
    def setUp(self):
        super().setUp()
        with use_operator():
            self.tenant = make_tenant("bitcoin-submission")
            self.wallet = Wallet.objects.create(
                user_account=self.tenant.account,
                chain="bitcoin",
                address=FIXTURE["sender"],
                verification_status="VERIFIED",
            )
            self.asset = native_asset_for_chain("bitcoin")
            self.holding = Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=Decimal("50"))
        self.client.force_authenticate(self.tenant.user)
        self.client.raise_request_exception = False
        self.provider = object.__new__(BitcoinClient)
        self.provider.expected_network = "regtest"
        self.provider._rpc_call = Mock(side_effect=self.rpc)
        self.input_script = FIXTURE["input"]["script"]
        self.preflight = FIXTURE["preflight"]
        self.acknowledged_hash = FIXTURE["txid"]
        self.before_send = lambda raw: None
        self.lost_acknowledgement = False
        self.rpc_overrides = {}
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
            "integrations.blockchain.factory.BlockchainClientFactory.get_client", return_value=self.provider
        )
        provider.start()
        self.addCleanup(provider.stop)

    def rpc(self, method, params=None):
        if method in self.rpc_overrides:
            result = self.rpc_overrides[method]
            return result(params) if callable(result) else result
        if method == "getblockchaininfo":
            return {"chain": "regtest"}
        if method == "getblockhash":
            self.assertEqual(params, [0])
            return REGTEST_GENESIS
        if method == "gettxout":
            self.assertEqual(params[:2], [FIXTURE["input"]["txid"], FIXTURE["input"]["vout"]])
            return {
                "bestblock": "48" * 32,
                "value": Decimal("50"),
                "scriptPubKey": {"hex": self.input_script},
                "confirmations": 101,
                "coinbase": True,
            }
        if method == "testmempoolaccept":
            self.assertEqual(params[0], [FIXTURE["raw_transaction"]])
            return [self.preflight]
        if method == "getrawtransaction":
            raise ConnectionError("Synthetic transaction has not been mined")
        if method == "sendrawtransaction":
            self.before_send(params[0])
            if self.lost_acknowledgement:
                raise TimeoutError("Synthetic Bitcoin acknowledgement loss")
            return self.acknowledged_hash
        raise AssertionError(f"Unexpected Bitcoin RPC method {method}")

    def broadcast(self, **extra):
        return self.client.post(
            f"/api/wallets/{self.wallet.pk}/broadcast-transfer/",
            {"signed_transaction": FIXTURE["raw_transaction"], **extra},
            format="json",
        )

    def transactions(self):
        with use_operator():
            return list(Transaction.objects.filter(wallet=self.wallet).values())

    def sent(self):
        return [
            call.args[1][0] for call in self.provider._rpc_call.call_args_list if call.args[0] == "sendrawtransaction"
        ]

    def quantity(self):
        with use_operator():
            self.holding.refresh_from_db()
        return self.holding.quantity

    def submission(self):
        with use_operator():
            return BitcoinSubmission.objects.get(wallet=self.wallet)

    def submit_direct(self, raw=None, *, wallet=None, principal_id=None):
        principal_id = principal_id or self.tenant.user.pk
        with acting_for(principal_id):
            return transfers.broadcast_transfer(
                wallet or self.wallet, raw or FIXTURE["raw_transaction"], principal_id=principal_id
            )


class BitcoinSubmissionChecks(BitcoinSubmissionFixture):
    def test_the_signed_identity_and_pending_row_exist_before_the_first_send(self):
        before_send = []
        journals = []

        def observe(raw):
            self.assertEqual(raw, FIXTURE["raw_transaction"])
            before_send.extend(self.transactions())
            if before_send:
                with use_operator():
                    journals.extend(apps.get_model("wallets", "BitcoinSubmission").objects.values())

        self.before_send = observe
        response = self.broadcast()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(before_send), 1)
        self.assertEqual((before_send[0]["tx_hash"], before_send[0]["status"]), (FIXTURE["txid"], "pending"))
        self.assertEqual(len(journals), 1)
        self.assertEqual(bytes(journals[0]["raw_transaction"]), bytes.fromhex(FIXTURE["raw_transaction"]))
        self.assertEqual(journals[0]["tx_hash"], FIXTURE["txid"])
        self.assertEqual(journals[0]["witness_hash"], FIXTURE["wtxid"])

    def test_signed_outputs_and_previous_values_define_accounting_without_caller_metadata(self):
        response = self.broadcast(to_address=FIXTURE["sender"], amount="999", transaction_fee="40")
        self.assertEqual(response.status_code, 200)
        tx = self.transactions()[0]
        self.assertEqual(
            (tx["to_address"], tx["amount"], tx["transaction_fee_estimated"]),
            (FIXTURE["recipient"], Decimal("2"), Decimal("0.0001")),
        )
        self.assertEqual(self.quantity(), Decimal("47.9999"))

    def test_a_lost_acknowledgement_keeps_the_original_identity_and_debit(self):
        self.lost_acknowledgement = True
        response = self.broadcast()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], FIXTURE["txid"])
        self.assertEqual(len(self.transactions()), 1)
        self.assertEqual(self.quantity(), Decimal("47.9999"))

    def test_a_witness_hash_acknowledgement_never_replaces_the_local_transaction_id(self):
        self.acknowledged_hash = FIXTURE["wtxid"]
        response = self.broadcast()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["txHash"], FIXTURE["txid"])
        self.assertEqual(self.transactions()[0]["tx_hash"], FIXTURE["txid"])
        self.assertIsNone(self.submission().acknowledged_at)

    def test_foreign_inputs_are_refused_before_broadcast_or_accounting(self):
        self.input_script = FIXTURE["outputs"][0]["script"]
        response = self.broadcast()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.transactions(), [])
        self.assertEqual(self.quantity(), Decimal("50"))

    def test_an_unverified_signed_transaction_is_not_broadcast(self):
        self.preflight = {**FIXTURE["preflight"], "allowed": False}
        response = self.broadcast()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.transactions(), [])

    def test_an_exact_retry_preserves_one_pending_row_and_one_deduction(self):
        self.assertEqual(self.broadcast().status_code, 200)
        first = self.transactions()
        self.assertEqual(len(first), 1)
        self.assertEqual(self.broadcast().status_code, 200)
        self.assertEqual(self.transactions(), first)
        self.assertEqual(self.quantity(), Decimal("47.9999"))
        self.assertEqual(self.sent(), [FIXTURE["raw_transaction"]] * 2)


@override_settings(BITCOIN_NETWORK="regtest")
class BitcoinSubmissionTest(BitcoinSubmissionChecks, APITransactionTestCase):
    pass


@override_settings(BITCOIN_NETWORK="regtest")
class ScopedBitcoinSubmissionTest(RunsOnTheScopedConnection, BitcoinSubmissionChecks, APITransactionTestCase):
    pass
