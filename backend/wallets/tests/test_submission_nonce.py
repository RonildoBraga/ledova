from unittest.mock import Mock, patch

from django.conf import settings
from django.db import connections
from django.test import SimpleTestCase
from rest_framework.test import APITransactionTestCase

from integrations.blockchain.ethereum import EthereumClient
from shared.db import current_alias, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Wallet, WalletSubmission
from wallets.tests.test_submission_durability import SubmissionFixture


class SubmissionNonceChecks(SubmissionFixture):
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
            {**observed, "block_number": True},
            {**observed, "block_hash": "0x1234"},
            {**observed, "chain_id": settings.BLOCKCHAIN_CHAIN_ID + 1},
            TimeoutError("Synthetic nonce outage"),
        ):
            with self.subTest(invalid=invalid):
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
        self.assertEqual(transaction_states, [(False, before)])
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
        self.assertIn("wallet changed", response.json()["detail"])
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
        return client

    def test_nonce_uses_the_captured_mined_height_and_keeps_its_block_identity(self):
        client = self.make_chain_client()
        address = "0x" + "12" * 20
        self.assertEqual(
            client.get_mined_nonce(address),
            {"chain_id": 31337, "nonce": 3, "block_number": 7, "block_hash": "0x" + "ab" * 32},
        )
        client.w3.eth.get_transaction_count.assert_called_once_with(address, 7)
        self.assertEqual([c.args for c in client.w3.eth.get_block.call_args_list], [("latest",), ("latest",)])

    def test_changing_head_network_or_invalid_nonce_is_not_usable(self):
        for scenario in ("head", "network", "boolean", "negative", "overflow", "missing_head"):
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
                else:
                    client.w3.eth.get_transaction_count.return_value = {
                        "boolean": True,
                        "negative": -1,
                        "overflow": 2**64,
                    }[scenario]
                with self.assertRaises((ValueError, ConnectionError)):
                    client.get_mined_nonce("0x" + "12" * 20)
