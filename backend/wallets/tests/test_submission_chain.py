import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.test import override_settings
from hexbytes import HexBytes
from rest_framework.test import APITransactionTestCase
from web3 import Web3
from web3.exceptions import Web3RPCError

from assets.models import Asset, AssetChainDeployment
from integrations.blockchain import BlockchainClientFactory
from integrations.blockchain.ethereum import EthereumClient
from shared.db import acting_for, use_operator
from shared.tests.signed_transactions import high_s_transaction
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Transaction
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
        self.w3.manager.request_blocking("hardhat_setBalance", [self.signer.address, hex(10 * 10**18)])
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

    def test_node_rejected_high_s_signatures_cannot_reserve_funds_and_canonical_twins_mine(self):
        for nonce, fields in (
            (0, {}),
            (1, {"type": 1}),
            (2, {"type": 2, "maxFeePerGas": 2 * 10**9, "maxPriorityFeePerGas": 10**9}),
        ):
            with self.subTest(nonce=nonce):
                valid = self.signed(nonce=nonce, value=1, **fields)
                altered = HexBytes(high_s_transaction(bytes(valid.raw_transaction)))
                before = self.financial_state()
                with self.assertRaisesRegex(Web3RPCError, "signature|Signature|sender"):
                    self.w3.eth.send_raw_transaction(altered)
                self.assertEqual(self.w3.eth.get_transaction_count(self.signer.address), nonce)
                with patch("wallets.services.submissions.get_blockchain_client") as connect:
                    with self.assertRaisesRegex(InvalidTransactionException, "could not be decoded"):
                        self.submit_direct(SimpleNamespace(raw_transaction=altered))
                    connect.assert_not_called()
                self.assertEqual(self.financial_state(), before)
                result = self.submit_direct(valid)
                self.assertEqual(result["txHash"], valid.hash.to_0x_hex())
                receipt = self.w3.eth.get_transaction_receipt(result["txHash"])
                self.assertEqual(receipt.status, 1)
                self.assertEqual(self.w3.eth.get_transaction_count(self.signer.address), nonce + 1)

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
