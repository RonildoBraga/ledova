import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITransactionTestCase
from web3 import Web3
from web3.exceptions import Web3RPCError

from assets.models import Asset, AssetChainDeployment
from integrations.blockchain import BlockchainClientFactory
from integrations.blockchain.ethereum import EthereumClient
from shared.db import acting_for, use_operator
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Transaction, WalletChainObservation
from wallets.services.chain_observations import observe_wallet_chain
from wallets.services.holdings import sync_holding
from wallets.services.submissions import attempt_submission
from wallets.tasks.confirmation import confirm_pending_transaction
from wallets.tests.test_submission_durability import SubmissionFixture

RPC_URL = os.environ.get("CHAIN_TEST_RPC_URL", "")
TOKEN_ADDRESS = os.environ.get("STABLECOIN_CONTRACT_ADDRESS", "")

TOKEN_ABI = [
    {
        "type": "function",
        "name": "mint",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


@skipUnless(RPC_URL and TOKEN_ADDRESS, "A local chain and deployed test stablecoin are required")
@override_settings(BLOCKCHAIN_RPC_URL=RPC_URL, BLOCKCHAIN_CHAIN_ID=31337)
class SubmissionChainTest(SubmissionFixture, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        BlockchainClientFactory._clients.clear()
        self.addCleanup(BlockchainClientFactory._clients.clear)
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.assertEqual(self.w3.eth.chain_id, 31337)
        snapshot = self.w3.manager.request_blocking("evm_snapshot", [])
        self.addCleanup(self.w3.manager.request_blocking, "evm_revert", [snapshot])
        funding = self.w3.eth.send_transaction(
            {"from": self.w3.eth.accounts[0], "to": self.signer.address, "value": 10 * 10**18}
        )
        self.assertEqual(self.w3.eth.wait_for_transaction_receipt(funding).status, 1)
        with use_operator():
            self.native.is_verified = True
            self.native.save(update_fields=["is_verified"])

    def confirm(self, tx_hash):
        with patch("wallets.services.transaction_confirmation.sync_holding", wraps=sync_holding):
            return confirm_pending_transaction(tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)

    def assert_block_metadata(self, tx, receipt):
        block = self.w3.eth.get_block(receipt.blockHash)
        self.assertEqual(tx.block_hash, receipt.blockHash.to_0x_hex())
        self.assertEqual(tx.block_number, receipt.blockNumber)
        self.assertEqual(tx.block_timestamp, datetime.fromtimestamp(block.timestamp, tz=timezone.utc))
        self.assertEqual(tx.transaction_fee, Decimal(receipt.gasUsed * receipt.effectiveGasPrice) / Decimal(10**18))

    def test_intrinsically_invalid_gas_is_refused_before_reserving_funds_and_exact_limits_mine(self):
        access_list = [
            {"address": self.recipient, "storageKeys": ["0x" + "00" * 32] * 2},
            {"address": self.recipient, "storageKeys": ["0x" + "00" * 32] * 2},
        ]
        for nonce, fields, minimum in (
            (0, {}, 21000),
            (1, {"type": 1, "accessList": access_list}, 33400),
            (
                2,
                {"type": 2, "maxFeePerGas": 2 * 10**9, "maxPriorityFeePerGas": 10**9, "accessList": access_list},
                33400,
            ),
        ):
            with self.subTest(nonce=nonce):
                invalid = self.signed(nonce=nonce, value=0, gas=minimum - 1, **fields)
                before = self.financial_state()
                with self.assertRaisesRegex(Web3RPCError, "gas|Gas"):
                    self.w3.eth.send_raw_transaction(invalid.raw_transaction)
                self.assertEqual(self.w3.eth.get_transaction_count(self.signer.address), nonce)
                with patch("wallets.services.submissions.get_blockchain_client") as connect:
                    with self.assertRaisesRegex(InvalidTransactionException, "intrinsic gas"):
                        self.submit_direct(invalid)
                    connect.assert_not_called()
                self.assertEqual(self.financial_state(), before)
                valid = self.signed(nonce=nonce, value=0, gas=minimum, **fields)
                result = self.submit_direct(valid)
                receipt = self.w3.eth.get_transaction_receipt(result["txHash"])
                self.assertEqual((receipt.status, receipt.gasUsed), (1, minimum))

    def test_a_lost_node_acknowledgement_reconciles_the_original_mined_hash(self):
        signed = self.signed(nonce=0, gas=90000)
        send = EthereumClient.broadcast_transaction

        def lost_acknowledgement(client, raw):
            send(client, raw)
            raise TimeoutError("Synthetic acknowledgement lost after actual local mining")

        with patch.object(EthereumClient, "broadcast_transaction", lost_acknowledgement):
            result = self.submit_direct(signed)
        submission = self.submission()
        self.assertEqual(result["txHash"], signed.hash.to_0x_hex())
        self.assertIsNone(submission.acknowledged_at)
        self.assertEqual(self.w3.eth.get_transaction_count(self.signer.address), 1)
        receipt = self.w3.eth.get_transaction_receipt(submission.tx_hash)
        self.assertEqual(receipt.status, 1)
        self.assertEqual(self.w3.eth.get_balance(self.recipient), 2 * 10**18)
        with (
            acting_for(self.tenant.user.pk),
            patch.object(EthereumClient, "broadcast_transaction", wraps=send) as resent,
        ):
            self.assertEqual(attempt_submission(submission.pk), "receipt_available")
            resent.assert_not_called()
        self.assertEqual(self.confirm(submission.tx_hash)["status"], "confirmed")
        with use_operator():
            tx = Transaction.objects.get(pk=submission.transaction_id)
            self.holding.refresh_from_db()
        actual_fee = Decimal(receipt.gasUsed * receipt.effectiveGasPrice) / Decimal(10**18)
        self.assertEqual(tx.transaction_fee, actual_fee)
        self.assert_block_metadata(tx, receipt)
        self.assertEqual(self.holding.quantity, Decimal(self.w3.eth.get_balance(self.signer.address)) / Decimal(10**18))
        self.assertIsNone(tx.balance_reconciliation_token)
        before = self.financial_state()
        self.assertEqual(self.confirm(submission.tx_hash)["status"], "already_processed")
        self.assertEqual(self.financial_state(), before)

    def test_zero_fee_caps_are_rejected_while_zero_priority_fee_can_mine(self):
        before = self.financial_state()
        for fields in (
            {"gasPrice": 0},
            {"type": 1, "gasPrice": 0},
            {"type": 2, "maxFeePerGas": 0, "maxPriorityFeePerGas": 0},
        ):
            with self.subTest(fields=fields):
                signed = self.signed(nonce=0, **fields)
                with self.assertRaisesRegex(Web3RPCError, "fee|Fee|gasPrice"):
                    self.w3.eth.send_raw_transaction(signed.raw_transaction)
                with self.assertRaisesRegex(InvalidTransactionException, "fee cap"):
                    self.submit_direct(signed)
                self.assertEqual(self.financial_state(), before)
        signed = self.signed(nonce=0, type=2, maxFeePerGas=2 * 10**9, maxPriorityFeePerGas=0)
        result = self.submit_direct(signed)
        receipt = self.w3.eth.get_transaction_receipt(result["txHash"])
        self.assertEqual(receipt.status, 1)

    def test_an_external_mined_nonce_is_refused_before_reservation_and_the_next_nonce_works(self):
        external = self.signed(nonce=0, value=0)
        self.w3.eth.send_raw_transaction(external.raw_transaction)
        self.assertEqual(self.w3.eth.get_transaction_receipt(external.hash).status, 1)
        self.assertEqual(self.w3.eth.get_transaction_count(self.signer.address, "latest"), 1)
        before = self.financial_state()
        with patch.object(EthereumClient, "broadcast_transaction") as send:
            with self.assertRaisesRegex(InvalidTransactionException, "already been consumed"):
                self.submit_direct(self.signed(nonce=0))
            send.assert_not_called()
        self.assertEqual(self.financial_state(), before)
        signed = self.signed(nonce=1)
        result = self.submit_direct(signed)
        receipt = self.w3.eth.get_transaction_receipt(result["txHash"])
        self.assertEqual(receipt.status, 1)
        self.assertEqual(self.submission().intent["mined_nonce_observation"]["nonce"], 1)
        before = self.financial_state()
        with patch.object(EthereumClient, "get_mined_nonce") as nonce_read:
            self.assertEqual(self.submit_direct(signed), result)
            nonce_read.assert_not_called()
        self.assertEqual(self.financial_state(), before)

    def test_external_fee_bumps_and_zero_value_self_calls_have_bound_observation_evidence(self):
        entries = [{"address": self.recipient, "storageKeys": ["0x" + "00" * 32] * 2}] * 2
        envelopes = (
            ({}, {"gasPrice": 4 * 10**9}),
            ({"type": 1, "accessList": entries}, {"gasPrice": 4 * 10**9}),
            (
                {"type": 2, "maxFeePerGas": 2 * 10**9, "maxPriorityFeePerGas": 10**9, "accessList": entries},
                {"maxFeePerGas": 4 * 10**9, "maxPriorityFeePerGas": 2 * 10**9},
            ),
        )
        nonce = 0
        for kind in ("fee_bump", "zero_value_self_call"):
            for fields, bumped in envelopes:
                with self.subTest(kind=kind, envelope=fields.get("type", 0)):
                    original = self.signed(nonce=nonce, gas=90000, value=10**17, **fields)
                    replacement_fields = {**fields, **bumped}
                    if kind == "zero_value_self_call":
                        replacement_fields.update(to=self.signer.address, value=0)
                    else:
                        replacement_fields["value"] = 10**17
                    replacement = self.signed(nonce=nonce, gas=90000, **replacement_fields)
                    self.w3.manager.request_blocking("evm_setAutomine", [False])
                    try:
                        self.submit_direct(original)
                        before = self.financial_state()
                        self.w3.eth.send_raw_transaction(replacement.raw_transaction)
                        self.w3.manager.request_blocking("evm_mine", [])
                    finally:
                        self.w3.manager.request_blocking("evm_setAutomine", [True])
                    receipt = self.w3.eth.get_transaction_receipt(replacement.hash)
                    self.assertEqual(receipt.status, 1)
                    with use_operator():
                        tx = Transaction.objects.get(wallet=self.wallet, tx_hash=original.hash.to_0x_hex())
                    with patch.object(EthereumClient, "broadcast_transaction") as send:
                        self.assertEqual(observe_wallet_chain(tx.pk), "recorded")
                        send.assert_not_called()
                    with use_operator():
                        observation = WalletChainObservation.objects.get(watch__transaction=tx)
                    evidence = observation.evidence["nonce_spend"]
                    self.assertEqual(evidence["result"], "candidate", evidence)
                    self.assertEqual(evidence["candidate"]["tx_hash"], replacement.hash.to_0x_hex())
                    self.assertEqual(evidence["candidate"]["intent_kind"], kind)
                    self.assertEqual(evidence["candidate"]["block"]["hash"], receipt.blockHash.to_0x_hex())
                    self.assertEqual(self.financial_state(), before)
                    nonce += 1

    def test_funding_reorg_after_admission_preserves_the_journal_until_the_same_bytes_can_mine(self):
        signed = self.signed(nonce=0)
        self.w3.manager.request_blocking("hardhat_setBalance", [self.signer.address, "0x0"])
        self.w3.manager.request_blocking("evm_mine", [])
        unfunded = self.w3.manager.request_blocking("evm_snapshot", [])
        funding = self.w3.eth.send_transaction(
            {"from": self.w3.eth.accounts[0], "to": self.signer.address, "value": 10 * 10**18}
        )
        self.assertEqual(self.w3.eth.wait_for_transaction_receipt(funding).status, 1)
        send = EthereumClient.broadcast_transaction
        rejections = []
        reorgs = []

        def lose_funding(client, raw):
            reorgs.append(self.w3.manager.request_blocking("evm_revert", [unfunded]))
            try:
                return send(client, raw)
            except Web3RPCError as error:
                rejections.append(str(error))
                raise

        with patch.object(EthereumClient, "broadcast_transaction", lose_funding):
            result = self.submit_direct(signed)
        self.assertEqual(reorgs, [True])
        self.assertEqual(len(rejections), 1)
        self.assertRegex(rejections[0], "funds|balance|enough")
        self.assertEqual(self.w3.eth.get_balance(self.signer.address), 0)
        self.assertEqual(result["status"], "pending")
        submission = self.submission()
        self.assertIsNone(submission.acknowledged_at)
        before = self.financial_state()
        funded_again = self.w3.eth.send_transaction(
            {"from": self.w3.eth.accounts[0], "to": self.signer.address, "value": 10 * 10**18}
        )
        self.assertEqual(self.w3.eth.wait_for_transaction_receipt(funded_again).status, 1)
        with acting_for(self.tenant.user.pk):
            self.assertEqual(attempt_submission(submission.pk), "acknowledged")
        self.assertEqual(self.w3.eth.get_transaction_receipt(signed.hash).status, 1)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(bytes(self.submission().raw_transaction), bytes(signed.raw_transaction))

    def test_unfunded_signed_bytes_are_refused_before_journalling_and_work_after_actual_funding(self):
        signed = self.signed(nonce=0)
        self.w3.manager.request_blocking("hardhat_setBalance", [self.signer.address, "0x0"])
        self.w3.manager.request_blocking("evm_mine", [])
        before = self.financial_state()
        with self.assertRaisesRegex(Web3RPCError, "funds|balance|enough"):
            self.w3.eth.send_raw_transaction(signed.raw_transaction)
        with patch.object(EthereumClient, "broadcast_transaction") as send:
            with self.assertRaisesRegex(InvalidTransactionException, "native balance"):
                self.submit_direct(signed)
            send.assert_not_called()
        self.assertEqual(self.financial_state(), before)
        funded = self.w3.eth.send_transaction(
            {"from": self.w3.eth.accounts[0], "to": self.signer.address, "value": 10 * 10**18}
        )
        self.assertEqual(self.w3.eth.wait_for_transaction_receipt(funded).status, 1)
        result = self.submit_direct(signed)
        self.assertEqual(result["txHash"], signed.hash.to_0x_hex())
        self.assertEqual(self.w3.eth.get_transaction_receipt(signed.hash).status, 1)
        self.assertEqual(bytes(self.submission().raw_transaction), bytes(signed.raw_transaction))

    def test_a_mined_revert_retains_its_real_block_and_fee_after_reconciliation(self):
        signed = self.signed(nonce=0, to=Web3.to_checksum_address(TOKEN_ADDRESS), gas=90000)
        result = self.submit_direct(signed)
        self.assertEqual(result["txHash"], signed.hash.to_0x_hex())
        submission = self.submission()
        receipt = self.w3.eth.get_transaction_receipt(submission.tx_hash)
        self.assertEqual(receipt.status, 0)
        self.assertEqual(self.confirm(submission.tx_hash)["status"], "failed")
        with use_operator():
            tx = Transaction.objects.get(pk=submission.transaction_id)
            self.holding.refresh_from_db()
        self.assert_block_metadata(tx, receipt)
        self.assertEqual(tx.amount, Decimal("2"))
        self.assertEqual(self.holding.quantity, Decimal(self.w3.eth.get_balance(self.signer.address)) / Decimal(10**18))
        self.assertIsNone(tx.balance_reconciliation_token)
        before = self.financial_state()
        self.assertEqual(self.confirm(submission.tx_hash)["status"], "already_processed")
        self.assertEqual(self.financial_state(), before)

    def test_an_erc20_submission_settles_its_real_token_and_native_balances(self):
        address = Web3.to_checksum_address(TOKEN_ADDRESS)
        contract = self.w3.eth.contract(address=address, abi=TOKEN_ABI)
        minted = contract.functions.mint(self.signer.address, 3_000_000).transact({"from": self.w3.eth.accounts[0]})
        self.assertEqual(self.w3.eth.wait_for_transaction_receipt(minted).status, 1)
        with use_operator():
            asset = Asset.objects.create(
                symbol="LJUSD", name="Local journal token", asset_type="erc20_token", decimals=18, is_verified=True
            )
            AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=address, decimals=6)
            token_holding = Holding.objects.create(wallet=self.wallet, asset=asset, quantity=Decimal("3"))
        data = (
            bytes.fromhex("a9059cbb") + bytes(12) + bytes.fromhex(self.recipient[2:]) + (1_500_000).to_bytes(32, "big")
        )
        signed = self.signed(nonce=0, to=address, value=0, data=data, gas=90000)
        result = self.submit_direct(signed)
        self.assertEqual(result["txHash"], signed.hash.to_0x_hex())
        self.assertEqual(contract.functions.balanceOf(self.recipient).call(), 1_500_000)
        submission = self.submission()
        self.assertEqual(submission.intent["asset_decimals"], 6)
        self.assertEqual(self.confirm(submission.tx_hash)["status"], "confirmed")
        with use_operator():
            self.holding.refresh_from_db()
            token_holding.refresh_from_db()
        self.assertEqual(token_holding.quantity, Decimal("1.5"))
        self.assertEqual(self.holding.quantity, Decimal(self.w3.eth.get_balance(self.signer.address)) / Decimal(10**18))

    @override_settings(WALLET_CHAIN_FINALITY_POLICIES={"evm:31337": {"mode": "depth", "depth": 1}})
    def test_continuing_observations_keep_real_reorg_and_new_inclusion_history(self):
        before_send = self.w3.manager.request_blocking("evm_snapshot", [])
        signed = self.signed(nonce=0, gas=90000)
        self.submit_direct(signed)
        submission = self.submission()
        self.assertEqual(self.confirm(submission.tx_hash)["status"], "confirmed")
        before = self.financial_state()
        with patch.object(EthereumClient, "broadcast_transaction") as sent:
            self.assertEqual(observe_wallet_chain(submission.transaction_id), "recorded")
            sent.assert_not_called()
        with use_operator():
            first = WalletChainObservation.objects.get(watch__transaction_id=submission.transaction_id)
        original = dict(first.evidence)
        self.assertEqual((first.result, first.finality), ("included", "satisfied"))
        self.assertTrue(self.w3.manager.request_blocking("evm_revert", [before_send]))
        self.w3.manager.request_blocking("evm_mine", [])
        with patch.object(EthereumClient, "broadcast_transaction") as sent:
            self.assertEqual(observe_wallet_chain(submission.transaction_id), "recorded")
            sent.assert_not_called()
        self.w3.eth.send_raw_transaction(signed.raw_transaction)
        self.assertEqual(observe_wallet_chain(submission.transaction_id), "recorded")
        with use_operator():
            rows = list(
                WalletChainObservation.objects.filter(watch__transaction_id=submission.transaction_id).order_by(
                    "generation"
                )
            )
        self.assertEqual([row.result for row in rows], ["included", "orphaned", "included"])
        self.assertEqual(rows[0].evidence, original)
        self.assertTrue(rows[1].evidence["previous_orphaned"])
        self.assertTrue(rows[2].evidence["previous_orphaned"])
        self.assertNotEqual(rows[2].evidence["receipt"]["hash"], first.evidence["receipt"]["hash"])
        self.assertEqual(self.financial_state(), before)
