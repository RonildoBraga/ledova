from functools import partial
from unittest.mock import Mock, patch

from django.db import connections
from django.test import TransactionTestCase, override_settings
from web3 import Web3

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from integrations.base_chain.client import BaseChainClient
from shared.db import atomic
from shared.db.aliases import current_alias
from shared.tests.tenants import make_tenant
from tokens.exceptions import TokenDeploymentFailedException
from tokens.models import ShareToken, ShareTokenStatus
from tokens.services import ShareTokenService
from tokens.tasks import deploy_share_token_task
from tokens.tests.test_deployment import CREATED, RECEIPT, SIGNER, factory

SIGNED_BYTES = b"synthetic deployment transaction"
SIGNED_HASH = Web3.to_hex(Web3.keccak(SIGNED_BYTES))


@override_settings(SHARE_TOKEN_FACTORY_ADDRESS="0x" + "f" * 40, BLOCKCHAIN_OPERATOR_KEY="synthetic-key")
class DeploymentSigningBoundaryTest(TransactionTestCase):
    def setUp(self):
        self.chain = Mock(spec=BaseChainClient)
        self.chain.account_from_key.return_value.address = SIGNER
        self.chain.get_address_from_private_key.return_value = SIGNER
        self.chain.sign_transaction.return_value = SIGNED_BYTES
        self.chain.send_raw_transaction.return_value = SIGNED_HASH
        self.chain.send_transaction.side_effect = partial(BaseChainClient.send_transaction, self.chain)
        self.chain.wait_for_receipt.return_value = RECEIPT
        self.chain.get_transaction_receipt.return_value = None
        self.factory = factory()
        self.factory.functions.authorizedShares.return_value.call.return_value = 1000
        self.chain.load_contract.return_value = self.factory
        client = patch("tokens.services.share_token_service.get_base_chain_client", return_value=self.chain)
        client.start()
        self.addCleanup(client.stop)
        approval = patch("tokens.services.share_token_service.ShareTokenService._approve_for_swap")
        approval.start()
        self.addCleanup(approval.stop)
        self.tenant = make_tenant("deployment-boundary")
        self.token = self.tenant.token
        self.token.mark_deploying()
        self.service = ShareTokenService()

    def test_success_records_the_confirmed_deployment_and_receipt(self):
        result = self.service.deploy_token(self.token)

        self.token.refresh_from_db()
        record = BlockchainTransaction.objects.get()
        self.assertEqual(result["contract_address"], CREATED)
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.token.deployment_transaction_id, record.pk)
        self.assertEqual((self.token.deployment_tx_hash, record.tx_hash), (SIGNED_HASH, SIGNED_HASH))
        self.assertEqual((record.status, record.block_number), (TransactionStatus.CONFIRMED, RECEIPT["blockNumber"]))
        self.chain.send_raw_transaction.assert_called_once_with(SIGNED_BYTES)
        self.chain.wait_for_receipt.assert_called_once_with(SIGNED_HASH)

    def test_success_broadcast_observes_the_committed_hash_and_association(self):
        observed = []

        def observe(raw):
            current = ShareToken.objects.get(pk=self.token.pk)
            record = BlockchainTransaction.objects.get()
            observed.append(
                (
                    raw,
                    connections[current_alias()].get_autocommit(),
                    current.deployment_tx_hash,
                    current.deployment_transaction_id,
                    record.tx_hash,
                    record.status,
                    record.pk,
                )
            )
            return SIGNED_HASH

        self.chain.send_raw_transaction.side_effect = observe
        result = self.service.deploy_token(self.token)

        record = BlockchainTransaction.objects.get()
        self.assertEqual(
            observed,
            [(SIGNED_BYTES, True, SIGNED_HASH, record.pk, SIGNED_HASH, TransactionStatus.SUBMITTED, record.pk)],
        )
        self.assertEqual(result["contract_address"], CREATED)
        self.assertEqual(record.status, TransactionStatus.CONFIRMED)
        self.chain.send_raw_transaction.assert_called_once_with(SIGNED_BYTES)

    def test_lost_send_acknowledgement_and_task_retry_keep_the_original_hash(self):
        accepted = []

        def accept_without_acknowledgement(raw):
            accepted.append(raw)
            raise ConnectionError("synthetic acknowledgement lost")

        self.chain.send_raw_transaction.side_effect = accept_without_acknowledgement
        with self.assertRaises(TokenDeploymentFailedException):
            self.service.deploy_token(self.token)

        self.token.refresh_from_db()
        record = BlockchainTransaction.objects.get()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, SIGNED_HASH))
        self.assertEqual((self.token.deployment_transaction_id, record.tx_hash), (record.pk, SIGNED_HASH))
        self.assertEqual(record.status, TransactionStatus.SUBMITTED)
        self.chain.wait_for_receipt.side_effect = TimeoutError("synthetic receipt unavailable")
        with self.assertRaises(TokenDeploymentFailedException):
            deploy_share_token_task(token_uuid=str(self.token.uuid))

        self.assertEqual(accepted, [SIGNED_BYTES])
        self.chain.wait_for_receipt.assert_called_once_with(SIGNED_HASH)
        self.assertEqual(BlockchainTransaction.objects.count(), 1)
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, SIGNED_HASH))

    def test_partial_hash_write_rolls_back_and_prevents_broadcast(self):
        mark_submitted = BlockchainTransaction.mark_submitted

        def save_then_fail(record, tx_hash):
            mark_submitted(record, tx_hash)
            raise RuntimeError("synthetic journal write failure")

        with patch.object(BlockchainTransaction, "mark_submitted", save_then_fail):
            with self.assertRaises((TokenDeploymentFailedException, RuntimeError)):
                self.service.deploy_token(self.token)

        self.chain.send_raw_transaction.assert_not_called()
        record = BlockchainTransaction.objects.get()
        self.token.refresh_from_db()
        self.assertFalse(record.tx_hash)
        self.assertIsNone(self.token.deployment_transaction_id)
        self.assertIsNone(self.token.deployment_tx_hash)
        self.assertEqual(self.token.status, ShareTokenStatus.DRAFT)

    def test_partial_binding_rolls_back_both_rows_before_a_safe_new_attempt(self):
        bind = ShareToken.bind_deployment_transaction

        def bind_then_fail(token, tx_hash, record):
            self.assertTrue(bind(token, tx_hash, record))
            raise RuntimeError("synthetic association write failure")

        with patch.object(ShareToken, "bind_deployment_transaction", bind_then_fail):
            with self.assertRaises((TokenDeploymentFailedException, RuntimeError)):
                self.service.deploy_token(self.token)

        self.chain.send_raw_transaction.assert_not_called()
        record = BlockchainTransaction.objects.get()
        self.token.refresh_from_db()
        self.assertFalse(record.tx_hash)
        self.assertIsNone(self.token.deployment_transaction_id)
        self.assertIsNone(self.token.deployment_tx_hash)
        self.token.mark_deploying()
        self.service.deploy_token(self.token)
        self.chain.send_raw_transaction.assert_called_once_with(SIGNED_BYTES)
        self.assertEqual(BlockchainTransaction.objects.count(), 2)

    def test_a_competing_binding_refuses_this_stale_attempt_before_broadcast(self):
        other = BlockchainTransaction.objects.create(
            tx_type=TransactionType.SHARE_TOKEN_DEPLOY,
            status=TransactionStatus.SUBMITTED,
            tx_hash="0x" + "ab" * 32,
            related_model="tokens.ShareToken",
            related_uuid=self.token.uuid,
        )

        def bind_other_before_callback(*args, **kwargs):
            current = ShareToken.objects.get(pk=self.token.pk)
            self.assertTrue(current.bind_deployment_transaction(other.tx_hash, other))
            return SIGNED_BYTES

        self.chain.sign_transaction.side_effect = bind_other_before_callback
        with self.assertRaises(TokenDeploymentFailedException):
            self.service.deploy_token(self.token)

        self.chain.send_raw_transaction.assert_not_called()
        self.token.refresh_from_db()
        self.assertEqual(self.token.deployment_transaction_id, other.pk)
        self.assertEqual(self.token.deployment_tx_hash, other.tx_hash)
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYING)
        refused = BlockchainTransaction.objects.exclude(pk=other.pk).get()
        self.assertFalse(refused.tx_hash)
        other.refresh_from_db()
        self.assertEqual(other.status, TransactionStatus.SUBMITTED)

    def test_pre_sign_failure_remains_an_unbound_draft_without_broadcast(self):
        self.chain.build_transaction.side_effect = RuntimeError("synthetic gas estimation failure")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "Token deployment failed."):
            self.service.deploy_token(self.token)

        self.chain.sign_transaction.assert_not_called()
        self.chain.send_raw_transaction.assert_not_called()
        self.token.refresh_from_db()
        record = BlockchainTransaction.objects.get()
        self.assertEqual(self.token.status, ShareTokenStatus.DRAFT)
        self.assertIsNone(self.token.deployment_tx_hash)
        self.assertFalse(record.tx_hash)
        self.assertEqual(record.status, TransactionStatus.FAILED)

    def test_an_outer_transaction_cannot_defer_the_pre_broadcast_commit(self):
        with atomic():
            with self.assertRaises(TokenDeploymentFailedException):
                self.service.deploy_token(self.token)

        self.chain.send_raw_transaction.assert_not_called()
        self.token.refresh_from_db()
        self.assertIsNone(self.token.deployment_tx_hash)

    def test_manual_autocommit_off_cannot_defer_the_pre_broadcast_commit(self):
        connection = connections[current_alias()]
        connection.set_autocommit(False)
        try:
            with self.assertRaises(TokenDeploymentFailedException):
                self.service.deploy_token(self.token)
            self.chain.send_raw_transaction.assert_not_called()
        finally:
            connection.rollback()
            connection.set_autocommit(True)

    def test_lost_commit_acknowledgement_blocks_send_and_retains_recovery(self):
        connection = connections[current_alias()]
        commit = connection.commit

        def commit_then_fail():
            commit()
            raise RuntimeError("synthetic commit acknowledgement lost")

        with patch.object(connection, "commit", side_effect=commit_then_fail):
            with self.assertRaises(TokenDeploymentFailedException):
                self.service.deploy_token(self.token)

        self.chain.send_raw_transaction.assert_not_called()
        self.token.refresh_from_db()
        record = BlockchainTransaction.objects.get()
        self.assertEqual(self.token.deployment_tx_hash, SIGNED_HASH)
        self.assertEqual(self.token.deployment_transaction_id, record.pk)
        self.assertEqual(record.tx_hash, SIGNED_HASH)
        self.chain.wait_for_receipt.side_effect = TimeoutError("synthetic receipt unavailable")
        with self.assertRaises(TokenDeploymentFailedException):
            deploy_share_token_task(token_uuid=str(self.token.uuid))
        self.chain.send_raw_transaction.assert_not_called()
        self.assertEqual(BlockchainTransaction.objects.count(), 1)

    def test_rpc_hash_mismatch_does_not_replace_the_pre_broadcast_identity(self):
        self.chain.send_raw_transaction.return_value = "0x" + "de" * 32
        with self.assertRaises(TokenDeploymentFailedException):
            self.service.deploy_token(self.token)

        self.token.refresh_from_db()
        record = BlockchainTransaction.objects.get()
        self.assertEqual(self.token.deployment_tx_hash, SIGNED_HASH)
        self.assertEqual(record.tx_hash, SIGNED_HASH)
        self.chain.wait_for_receipt.assert_not_called()
