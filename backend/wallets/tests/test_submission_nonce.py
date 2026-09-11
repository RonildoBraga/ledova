from unittest.mock import Mock, patch

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.test import SimpleTestCase
from rest_framework.test import APITransactionTestCase

from integrations.blockchain.ethereum import EthereumClient
from shared.db import current_alias, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Wallet, WalletSubmission
from wallets.tests.test_submission_durability import SubmissionFixture


class SubmissionNonceChecks(SubmissionFixture):
    def test_native_balance_covers_the_exact_signed_cost_before_any_reservation(self):
        for index, fields, price in (
            (0, {}, 2 * 10**9),
            (1, {"type": 1, "accessList": []}, 2 * 10**9),
            (2, {"type": 2, "maxFeePerGas": 4 * 10**9, "maxPriorityFeePerGas": 10**9}, 4 * 10**9),
        ):
            with self.subTest(envelope=index):
                signed = self.signed(nonce=3 + index, **fields)
                cost = 2 * 10**18 + 21000 * price
                provider = self.provider(signed)
                observed = {**provider.get_mined_nonce(self.signer.address), "nonce": 3 + index}
                provider.get_mined_nonce.side_effect = None
                provider.get_mined_nonce.return_value = {**observed, "balance_wei": str(cost - 1)}
                before = self.financial_state()
                with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
                    response = self.broadcast(signed)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("native balance", response.json()["detail"])
                    self.assertEqual(self.financial_state(), before)
                    provider.broadcast_transaction.assert_not_called()
                    provider.get_mined_nonce.return_value = {**observed, "balance_wei": str(cost)}
                    self.assertEqual(self.broadcast(signed).status_code, 200)
                    provider.broadcast_transaction.assert_called_once_with(signed.raw_transaction.to_0x_hex())

    def test_consumed_nonce_is_refused_without_a_journal_debit_or_send(self):
        signed = self.signed(nonce=3)
        provider = self.provider(signed)
        observed = provider.get_mined_nonce(self.signer.address)
        provider.get_mined_nonce.side_effect = None
        provider.get_mined_nonce.return_value = {**observed, "nonce": 4}
        before = self.financial_state()
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 400)
        self.assertIn("already been consumed", response.json()["detail"])
        self.assertEqual(self.financial_state(), before)
        with use_operator():
            self.assertFalse(WalletSubmission.objects.filter(wallet=self.wallet).exists())
        provider.broadcast_transaction.assert_not_called()

    def test_unavailable_or_malformed_nonce_evidence_cannot_reserve_funds(self):
        signed = self.signed()
        before = self.financial_state()
        observed = self.provider(signed).get_mined_nonce(self.signer.address)
        for invalid in (
            None,
            False,
            {"nonce": 0},
            *({**observed, "nonce": value} for value in (True, -1, 2**64)),
            *({**observed, "balance_wei": value} for value in (None, True, "-1", str(2**256))),
            {**observed, "block_number": True},
            {**observed, "block_hash": "0x1234"},
            {**observed, "chain_id": settings.BLOCKCHAIN_CHAIN_ID + 1},
            TimeoutError("Synthetic nonce outage"),
        ):
            with self.subTest(invalid=invalid):
                cache.clear()
                provider = self.provider(signed)
                provider.get_mined_nonce.side_effect = invalid if isinstance(invalid, Exception) else None
                provider.get_mined_nonce.return_value = invalid
                with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
                    self.assertEqual(self.broadcast(signed).status_code, 400)
                self.assertEqual(self.financial_state(), before)
                provider.broadcast_transaction.assert_not_called()

    def test_the_wrong_provider_network_is_refused_before_nonce_read_or_reservation(self):
        signed = self.signed()
        provider = self.provider(signed)
        provider.assert_expected_chain.return_value = settings.BLOCKCHAIN_CHAIN_ID + 1
        before = self.financial_state()
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            self.assertEqual(self.broadcast(signed).status_code, 400)
        self.assertEqual(self.financial_state(), before)
        provider.get_mined_nonce.assert_not_called()
        provider.broadcast_transaction.assert_not_called()

    def test_mined_nonce_evidence_is_captured_outside_a_database_transaction(self):
        signed = self.signed()
        provider = self.provider(signed)
        observed = provider.get_mined_nonce(self.signer.address)
        transaction_states = []

        def read(address):
            transaction_states.append((connections[current_alias()].in_atomic_block, self.financial_state()))
            return observed

        before = self.financial_state()
        provider.get_mined_nonce.side_effect = read
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(transaction_states[0], (False, before))
        self.assertEqual(len(transaction_states), 2)
        self.assertFalse(transaction_states[1][0])
        self.assertEqual(len(transaction_states[1][1][0]), len(before[0]) + 1)
        self.assertEqual(self.submission().intent["mined_nonce_observation"], observed)

    def test_an_exact_retry_uses_its_journal_even_when_the_nonce_is_now_consumed(self):
        signed = self.signed()
        provider = self.provider(signed)
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            first = self.submit_direct(signed)
            before = self.financial_state()
            provider.get_mined_nonce.reset_mock()
            provider.get_mined_nonce.side_effect = AssertionError("An existing journal must retain its identity")
            provider.get_transaction_receipt.return_value = {"transactionHash": signed.hash.to_0x_hex()}
            provider.broadcast_transaction.reset_mock()
            self.assertEqual(self.submit_direct(signed), first)
        self.assertEqual(self.financial_state(), before)
        provider.get_mined_nonce.assert_not_called()
        provider.broadcast_transaction.assert_not_called()

    def test_a_wallet_change_during_the_nonce_read_refuses_admission(self):
        signed = self.signed()
        provider = self.provider(signed)
        observed = provider.get_mined_nonce(self.signer.address)
        before = self.financial_state()

        def change_wallet(address):
            with use_operator():
                Wallet.objects.filter(pk=self.wallet.pk).update(verification_status="PENDING")
            return observed

        provider.get_mined_nonce.side_effect = change_wallet
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 400)
        self.assertIn("commitments changed", response.json()["detail"])
        self.assertEqual(self.financial_state(), before)
        provider.broadcast_transaction.assert_not_called()

    def test_membership_revoked_during_nonce_read_refuses_admission(self):
        signed = self.signed()
        provider = self.provider(signed)
        observed = provider.get_mined_nonce(self.signer.address)
        before = self.financial_state()

        def revoke_membership(address):
            with use_operator():
                self.tenant.account.user_profiles.clear()
            return observed

        provider.get_mined_nonce.side_effect = revoke_membership
        with patch("wallets.services.submissions.get_blockchain_client", return_value=provider):
            response = self.broadcast(signed)
        self.assertEqual(response.status_code, 400)
        self.assertIn("no longer available", response.json()["detail"])
        self.assertEqual(self.financial_state(), before)
        provider.broadcast_transaction.assert_not_called()


class SubmissionNonceTest(SubmissionNonceChecks, APITransactionTestCase):
    pass


class ScopedSubmissionNonceTest(RunsOnTheScopedConnection, SubmissionNonceChecks, APITransactionTestCase):
    pass


class MinedNonceReaderTest(SimpleTestCase):
    def make_chain_client(self):
        client = EthereumClient.__new__(EthereumClient)
        client.expected_chain_id = 31337
        client.w3 = Mock()
        client.w3.eth.chain_id = 31337
        client.w3.eth.get_block.return_value = {"number": 7, "hash": bytes.fromhex("ab" * 32)}
        client.w3.eth.get_transaction_count.return_value = 3
        client.w3.eth.get_balance.return_value = 10**19
        return client

    def test_nonce_uses_the_captured_mined_height_and_keeps_its_block_identity(self):
        client = self.make_chain_client()
        address = "0x" + "12" * 20
        self.assertEqual(
            client.get_mined_nonce(address),
            {
                "chain_id": 31337,
                "nonce": 3,
                "balance_wei": str(10**19),
                "block_number": 7,
                "block_hash": "0x" + "ab" * 32,
            },
        )
        client.w3.eth.get_transaction_count.assert_called_once_with(address, 7)
        client.w3.eth.get_balance.assert_called_once_with(address, 7)
        self.assertEqual([c.args for c in client.w3.eth.get_block.call_args_list], [("latest",), ("latest",)])

    def test_changing_head_network_or_invalid_nonce_is_not_usable(self):
        for scenario in (
            "head",
            "network",
            "boolean",
            "negative",
            "overflow",
            "missing_head",
            "balance_boolean",
            "balance_negative",
            "balance_overflow",
        ):
            with self.subTest(scenario=scenario):
                client = self.make_chain_client()
                if scenario == "head":
                    client.w3.eth.get_block.side_effect = [
                        {"number": 7, "hash": bytes.fromhex("ab" * 32)},
                        {"number": 7, "hash": bytes.fromhex("cd" * 32)},
                    ]
                elif scenario == "network":

                    def changed_chain(address, height):
                        client.w3.eth.chain_id = 31338
                        return 3

                    client.w3.eth.get_transaction_count.side_effect = changed_chain
                elif scenario == "missing_head":
                    client.w3.eth.get_block.return_value = {"number": 7}
                elif scenario.startswith("balance_"):
                    client.w3.eth.get_balance.return_value = {
                        "balance_boolean": True,
                        "balance_negative": -1,
                        "balance_overflow": 2**256,
                    }[scenario]
                else:
                    client.w3.eth.get_transaction_count.return_value = {
                        "boolean": True,
                        "negative": -1,
                        "overflow": 2**64,
                    }[scenario]
                with self.assertRaises((ValueError, ConnectionError)):
                    client.get_mined_nonce("0x" + "12" * 20)

    def test_token_balance_reads_use_the_same_bounded_height_as_nonce_and_native_balance(self):
        client = self.make_chain_client()
        address = "0x" + "12" * 20
        token = "0x" + "34" * 20
        balance_call = client.w3.eth.contract.return_value.functions.balanceOf.return_value.call
        balance_call.return_value = 1500000
        observed = client.get_mined_nonce(address, token_contracts=[token])
        self.assertEqual(observed["token_balances"], {token: "1500000"})
        self.assertEqual(observed["block_number"], 7)
        balance_call.assert_called_once_with(block_identifier=7)
        client.w3.eth.get_transaction_count.assert_called_once_with(address, 7)
        client.w3.eth.get_balance.assert_called_once_with(address, 7)

    def test_a_token_balance_from_a_changed_head_or_malformed_value_is_refused(self):
        for changed in (True, False):
            with self.subTest(changed_head=changed):
                client = self.make_chain_client()
                balance_call = client.w3.eth.contract.return_value.functions.balanceOf.return_value.call

                def read(**kwargs):
                    if changed:
                        client.w3.eth.get_block.return_value = {"number": 8, "hash": bytes.fromhex("cd" * 32)}
                        return 1500000
                    return True

                balance_call.side_effect = read
                with self.assertRaises(ValueError):
                    client.get_mined_nonce("0x" + "12" * 20, token_contracts=["0x" + "34" * 20])
