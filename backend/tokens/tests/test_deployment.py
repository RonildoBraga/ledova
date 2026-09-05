"""Deployment and its crash recovery, the pending-deployment sweep and pause/unpause with the chain client mocked."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from companies.models import Company
from shared.tests.tenants import make_tenant
from tokens.exceptions import (
    CompanyNotReadyException,
    InvalidTokenStateException,
    TokenDeploymentFailedException,
    TokenPauseFailedException,
)
from tokens.models import ShareIssuance, ShareToken, ShareTokenStatus
from tokens.services import ShareTokenService
from tokens.tasks import check_pending_token_deployments, deploy_share_token_task
from wallets.models import Wallet

CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
CREATED = "0x" + "c0ffee" + "0" * 34
SIGNER = "0x" + "e" * 40
RECEIPT = {"blockNumber": 9, "blockHash": bytes.fromhex("ab" * 32), "gasUsed": 1_000_000}
SWAP = "tokens.services.share_token_service.ShareTokenService._approve_for_swap"


def factory(existing=None, events=None):
    contract = Mock()
    contract.functions.getTokenByIdentifier.return_value.call.return_value = (
        existing or "0x0000000000000000000000000000000000000000"
    )
    contract.events.ShareTokenCreated.return_value.process_receipt.return_value = (
        [{"args": {"tokenAddress": CREATED}}] if events is None else events
    )
    return contract


@override_settings(SHARE_TOKEN_FACTORY_ADDRESS="0x" + "f" * 40, BLOCKCHAIN_OPERATOR_KEY="0xkey")
class DeployTokenTest(TestCase):
    def setUp(self):
        self.client_patch = patch(CHAIN_CLIENT)
        self.chain = self.client_patch.start().return_value
        self.addCleanup(self.client_patch.stop)
        self.chain.get_address_from_private_key.return_value = SIGNER
        self.chain.send_transaction.return_value = ("0xcreate", None)
        self.chain.wait_for_receipt.return_value = RECEIPT
        self.chain.get_transaction_receipt.return_value = None
        self.chain.load_contract.return_value.functions.authorizedShares.return_value.call.return_value = 1000
        patch(SWAP).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.token
        self.token.mark_deploying()

    def _service(self, contract):
        service = ShareTokenService()
        service._factory_contract = contract
        return service

    def _sent(self, tx_hash="0xsent"):
        """The state a crash after the create transaction leaves behind: DEPLOYING with a failed record."""
        record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.SHARE_TOKEN_DEPLOY,
            status=TransactionStatus.FAILED,
            tx_hash=tx_hash,
            from_address=SIGNER,
            to_address="0x" + "f" * 40,
            function_name="createShareToken",
            related_model="tokens.ShareToken",
            related_uuid=self.token.uuid,
        )
        self.token.mark_deploying(tx_hash=tx_hash, transaction=record)
        return record

    def test_identifier_is_acn_and_symbol_and_survives_a_later_abn(self):
        acn = self.tenant.company.acn
        self.assertEqual(ShareTokenService.token_identifier(self.token), f"{acn}:DRF")
        self.assertEqual(ShareTokenService.token_identifier(self.tenant.deployed_token), f"{acn}:DEP")
        Company.objects.filter(pk=self.tenant.company.pk).update(abn="12345678901")
        self.token.company.refresh_from_db()
        self.assertEqual(ShareTokenService.token_identifier(self.token), f"{acn}:DRF")

    def test_create_parses_the_event_and_records_the_transaction_without_minting(self):
        contract = factory()
        result = self._service(contract).deploy_token(self.token)

        self.assertEqual(
            result, {"contract_address": CREATED, "identifier": f"{self.tenant.company.acn}:DRF", "adopted": False}
        )
        contract.functions.createShareToken.assert_called_once_with(
            self.token.name, "DRF", f"{self.tenant.company.acn}:DRF", 1000, SIGNER
        )
        self.chain.send_transaction.assert_called_once_with(
            contract.functions.createShareToken.return_value, "0xkey", wait_for_receipt=False
        )
        self.chain.wait_for_receipt.assert_called_once_with("0xcreate")
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.contract_address), (ShareTokenStatus.DEPLOYED, CREATED))
        self.assertEqual(self.token.deployment_tx_hash, "0xcreate")
        record = BlockchainTransaction.objects.get()
        self.assertEqual(self.token.deployment_transaction, record)
        self.assertEqual(
            (record.tx_type, record.status), (TransactionType.SHARE_TOKEN_DEPLOY, TransactionStatus.CONFIRMED)
        )
        self.assertEqual((record.tx_hash, record.block_number, record.gas_used), ("0xcreate", 9, 1_000_000))
        self.assertEqual(record.function_args["issuerWallet"], self.tenant.wallet.address)
        self.assertEqual(record.function_args["authorizedShares"], "1000")
        self.assertEqual((record.related_model, record.related_uuid), ("tokens.ShareToken", self.token.uuid))
        self.assertFalse(ShareIssuance.objects.exists())

    def test_rerun_adopts_the_factory_address_without_sending(self):
        contract = factory(existing=CREATED)
        result = self._service(contract).deploy_token(self.token)

        self.assertEqual(result["adopted"], True)
        self.assertEqual(result["contract_address"], CREATED)
        contract.functions.createShareToken.assert_not_called()
        self.chain.send_transaction.assert_not_called()
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.contract_address), (ShareTokenStatus.DEPLOYED, CREATED))
        self.assertFalse(BlockchainTransaction.objects.exists())

    def test_failure_before_the_transaction_returns_to_draft_with_the_error(self):
        self.chain.send_transaction.side_effect = RuntimeError("nonce too low")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "nonce too low"):
            self._service(factory()).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.contract_address), (ShareTokenStatus.DRAFT, None))
        self.assertIsNone(self.token.deployment_tx_hash)
        record = BlockchainTransaction.objects.get()
        self.assertEqual((record.status, record.error_message), (TransactionStatus.FAILED, "nonce too low"))

    def test_unconfigured_key_and_failed_lookup_return_to_draft_before_any_transaction(self):
        with override_settings(BLOCKCHAIN_OPERATOR_KEY=""):
            with self.assertRaises(TokenDeploymentFailedException):
                self._service(factory()).deploy_token(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DRAFT)
        self.assertFalse(BlockchainTransaction.objects.exists())

        self.token.mark_deploying()
        contract = factory()
        contract.functions.getTokenByIdentifier.return_value.call.side_effect = ConnectionError("rpc down")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "rpc down"):
            self._service(contract).deploy_token(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DRAFT)
        self.chain.send_transaction.assert_not_called()

    def test_missing_wallet_returns_to_draft_before_any_transaction(self):
        Company.objects.filter(pk=self.tenant.company.pk).update(operator_wallet=None)
        Wallet.objects.filter(user_account=self.tenant.account).update(chain="bitcoin")
        self.token.company.refresh_from_db()
        with self.assertRaises(CompanyNotReadyException):
            self._service(factory()).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DRAFT)
        self.chain.send_transaction.assert_not_called()

    def test_lost_receipt_after_sending_leaves_the_token_deploying(self):
        self.chain.wait_for_receipt.side_effect = RuntimeError("timeout")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "timeout"):
            self._service(factory()).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, "0xcreate"))
        record = BlockchainTransaction.objects.get()
        self.assertEqual(
            (record.status, record.tx_hash, record.error_message), (TransactionStatus.FAILED, "0xcreate", "timeout")
        )

    def test_receipt_without_the_event_leaves_the_token_deploying(self):
        with self.assertRaisesMessage(TokenDeploymentFailedException, "No ShareTokenCreated event"):
            self._service(factory(events=[])).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYING)

    def test_lookup_failure_after_sending_keeps_the_token_deploying_without_sending(self):
        self._sent()
        contract = factory()
        contract.functions.getTokenByIdentifier.return_value.call.side_effect = ConnectionError("rpc down")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "rpc down"):
            self._service(contract).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, "0xsent"))
        contract.functions.createShareToken.assert_not_called()
        self.chain.send_transaction.assert_not_called()

    def test_retry_resumes_on_the_recorded_transaction_instead_of_sending_again(self):
        record = self._sent()
        result = self._service(factory()).deploy_token(self.token)

        self.assertEqual((result["adopted"], result["contract_address"]), (False, CREATED))
        self.chain.wait_for_receipt.assert_called_once_with("0xsent")
        self.chain.send_transaction.assert_not_called()
        self.token.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(
            (self.token.status, self.token.contract_address, self.token.deployment_tx_hash),
            (ShareTokenStatus.DEPLOYED, CREATED, "0xsent"),
        )
        self.assertEqual((record.status, record.block_number), (TransactionStatus.CONFIRMED, 9))
        self.assertEqual(BlockchainTransaction.objects.count(), 1)

    def test_resume_on_an_unconfirmed_transaction_keeps_the_token_deploying(self):
        record = self._sent()
        self.chain.wait_for_receipt.side_effect = RuntimeError("still pending")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "still pending"):
            self._service(factory()).deploy_token(self.token)

        self.token.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, "0xsent"))
        self.assertEqual((record.status, record.error_message), (TransactionStatus.FAILED, "still pending"))
        self.chain.send_transaction.assert_not_called()

    def test_resume_on_a_reverted_transaction_discards_it_and_sends_a_fresh_create(self):
        record = self._sent()
        self.chain.get_transaction_receipt.return_value = {"status": 0}
        result = self._service(factory()).deploy_token(self.token)

        self.assertEqual((result["adopted"], result["contract_address"]), (False, CREATED))
        self.chain.send_transaction.assert_called_once()
        self.token.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYED, "0xcreate"))
        self.assertEqual(record.status, TransactionStatus.REVERTED)
        self.assertEqual(self.token.deployment_transaction.tx_hash, "0xcreate")
        self.assertEqual(BlockchainTransaction.objects.count(), 2)

    def test_adopting_a_token_whose_cap_differs_on_chain_is_logged(self):
        self.chain.load_contract.return_value.functions.authorizedShares.return_value.call.return_value = 999
        with self.assertLogs("tokens.services.share_token_service", "WARNING") as logs:
            result = self._service(factory(existing=CREATED)).deploy_token(self.token)

        self.assertEqual(result["adopted"], True)
        self.assertIn("authorises 999 shares on chain but 1000 in the database", logs.output[0])
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)

    def test_a_send_that_fails_after_another_worker_bound_a_create_does_not_draft_the_token(self):
        """Two deploy workers: the first binds its hash while the second's send is out; the second's send fails."""
        other = BlockchainTransaction.objects.create(
            tx_type=TransactionType.SHARE_TOKEN_DEPLOY,
            status=TransactionStatus.SUBMITTED,
            tx_hash="0xother",
            from_address=SIGNER,
            to_address="0x" + "f" * 40,
            function_name="createShareToken",
            related_model="tokens.ShareToken",
            related_uuid=self.token.uuid,
        )

        def other_worker_binds_then_this_send_fails(*args, **kwargs):
            ShareToken.objects.filter(pk=self.token.pk).update(
                deployment_tx_hash="0xother", deployment_transaction=other
            )
            raise RuntimeError("nonce too low")

        self.chain.send_transaction.side_effect = other_worker_binds_then_this_send_fails
        self.assertIsNone(self.token.deployment_tx_hash)
        with self.assertRaisesMessage(TokenDeploymentFailedException, "nonce too low"):
            self._service(factory()).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, "0xother"))
        self.assertEqual(self.token.deployment_transaction, other)
        self.assertEqual(BlockchainTransaction.objects.exclude(pk=other.pk).get().status, TransactionStatus.FAILED)

    def test_two_creates_sent_in_one_window_keep_the_hash_of_the_one_that_confirms(self):
        """A "Retry Deployment" click while the first worker is alive: both find nothing recorded and both send."""
        other = BlockchainTransaction.objects.create(
            tx_type=TransactionType.SHARE_TOKEN_DEPLOY,
            status=TransactionStatus.PENDING,
            tx_hash="0xother",
            from_address=SIGNER,
            to_address="0x" + "f" * 40,
            function_name="createShareToken",
            related_model="tokens.ShareToken",
            related_uuid=self.token.uuid,
        )

        hashes = iter(["0xcreate", "0xsecond"])

        def other_worker_writes_first(*args, **kwargs):
            ShareToken.objects.filter(pk=self.token.pk).update(
                deployment_tx_hash="0xother", deployment_transaction=other
            )
            return (next(hashes), None)

        self.chain.send_transaction.side_effect = other_worker_writes_first
        self.chain.wait_for_receipt.side_effect = RuntimeError("Transaction failed: 0xcreate (status=0)")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "status=0"):
            self._service(factory()).deploy_token(self.token)

        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, "0xother"))
        self.assertEqual(self.token.deployment_transaction, other)
        self.assertEqual(BlockchainTransaction.objects.get(tx_hash="0xcreate").status, TransactionStatus.FAILED)

        ShareToken.objects.filter(pk=self.token.pk).update(deployment_tx_hash=None, deployment_transaction=None)
        self.token.refresh_from_db()
        self.chain.wait_for_receipt.side_effect = None
        self.chain.wait_for_receipt.return_value = RECEIPT
        result = self._service(factory()).deploy_token(self.token)

        self.assertEqual(result["contract_address"], CREATED)
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYED, "0xsecond"))
        self.assertEqual(
            (self.token.deployment_transaction.tx_hash, self.token.deployment_transaction.status),
            ("0xsecond", TransactionStatus.CONFIRMED),
        )

    def test_task_guards_and_delegates(self):
        self.assertEqual(
            deploy_share_token_task(token_uuid="00000000-0000-0000-0000-000000000000"),
            {"success": False, "error": "Token not found"},
        )
        self.assertEqual(
            deploy_share_token_task(token_uuid=str(self.tenant.deployed_token.uuid)),
            {"success": False, "error": "Token is not in deploying state"},
        )
        outcome = {"contract_address": CREATED, "identifier": "x:DRF", "adopted": False}
        with patch.object(ShareTokenService, "deploy_token", return_value=outcome) as deploy:
            self.assertEqual(deploy_share_token_task(token_uuid=str(self.token.uuid)), {"success": True, **outcome})
        self.assertEqual(deploy.call_args.args[0], self.token)


class PendingDeploymentSweepTest(TestCase):
    def setUp(self):
        patch(CHAIN_CLIENT).start()
        patch(SWAP).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.token
        self.token.mark_deploying()

    def _age(self, token, minutes):
        ShareToken.objects.filter(pk=token.pk).update(updated_at=timezone.now() - timedelta(minutes=minutes))

    def test_stale_deploying_rows_resolve_through_the_identifier(self):
        self._age(self.token, 11)
        with patch.object(ShareTokenService, "get_token_by_identifier", return_value=CREATED) as lookup:
            self.assertEqual(check_pending_token_deployments(), {"checked": 1, "resolved": 1})
        lookup.assert_called_once_with(f"{self.tenant.company.acn}:DRF")
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.contract_address), (ShareTokenStatus.DEPLOYED, CREATED))

    def test_resolving_confirms_the_deploy_record_a_lost_receipt_left_failed(self):
        record = BlockchainTransaction.objects.create(
            tx_type=TransactionType.SHARE_TOKEN_DEPLOY, status=TransactionStatus.FAILED, tx_hash="0xsent"
        )
        self.token.mark_deploying(tx_hash="0xsent", transaction=record)
        self._age(self.token, 11)
        chain = ShareTokenService().chain_client
        chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}
        with patch.object(ShareTokenService, "get_token_by_identifier", return_value=CREATED):
            self.assertEqual(check_pending_token_deployments(), {"checked": 1, "resolved": 1})
        chain.get_transaction_receipt.assert_called_once_with("0xsent")
        record.refresh_from_db()
        self.assertEqual((record.status, record.block_number), (TransactionStatus.CONFIRMED, 9))
        self.assertEqual(record.block_hash, "0x" + "ab" * 32)

    def test_fresh_unbound_and_failing_rows_are_left_alone(self):
        with patch.object(ShareTokenService, "get_token_by_identifier", return_value=None) as lookup:
            self.assertEqual(check_pending_token_deployments(), {"checked": 0, "resolved": 0})
        lookup.assert_not_called()

        self._age(self.token, 11)
        with patch.object(ShareTokenService, "get_token_by_identifier", return_value=None):
            self.assertEqual(check_pending_token_deployments(), {"checked": 1, "resolved": 0})
        with patch.object(ShareTokenService, "get_token_by_identifier", side_effect=RuntimeError("rpc down")):
            self.assertEqual(check_pending_token_deployments(), {"checked": 1, "resolved": 0})
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYING)


@override_settings(BLOCKCHAIN_OPERATOR_KEY="0xkey")
class PauseTest(TestCase):
    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.addCleanup(patch.stopall)
        self.chain.send_transaction.return_value = ("0xpause", RECEIPT)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token
        self.service = ShareTokenService()
        self._chain_paused(False)

    def _contract(self):
        return self.chain.load_contract.return_value

    def _chain_paused(self, *states):
        reads = self._contract().functions.paused.return_value.call
        reads.side_effect = list(states[:-1]) + [states[-1]] * 8

    def test_pause_and_unpause_send_the_owner_calls_then_move_status(self):
        self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.PAUSED)
        self.chain.send_transaction.assert_called_once_with(
            self._contract().functions.pause.return_value, "0xkey", wait_for_receipt=True
        )

        self._chain_paused(True)
        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.chain.send_transaction.call_args.args[0], self._contract().functions.unpause.return_value)

    def test_chain_failure_keeps_the_status_and_surfaces(self):
        self.chain.send_transaction.side_effect = RuntimeError("execution reverted")
        with self.assertRaisesMessage(TokenPauseFailedException, "Token pause failed: execution reverted"):
            self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)

    def test_receipt_lost_after_the_call_mined_reconciles_the_status(self):
        self.chain.send_transaction.side_effect = RuntimeError("rpc timed out")
        self._chain_paused(False, True)
        self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.PAUSED)
        self.chain.send_transaction.assert_called_once()

        self._chain_paused(True, False)
        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)

    def test_chain_already_in_the_target_state_is_reconciled_without_sending(self):
        self._chain_paused(True)
        self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.PAUSED)

        self._chain_paused(False)
        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.chain.send_transaction.assert_not_called()

    def test_deployed_token_the_chain_reports_paused_can_be_unpaused(self):
        self._chain_paused(True)
        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.chain.send_transaction.call_args.args[0], self._contract().functions.unpause.return_value)

    def test_unreadable_paused_state_surfaces_before_any_call(self):
        self._contract().functions.paused.return_value.call.side_effect = ConnectionError("rpc down")
        with self.assertRaisesMessage(TokenPauseFailedException, "Token paused state could not be read: rpc down"):
            self.service.pause(self.token)
        self.chain.send_transaction.assert_not_called()

    def test_wrong_state_is_refused_before_any_call(self):
        with self.assertRaises(InvalidTokenStateException):
            self.service.unpause(self.token)
        with self.assertRaises(InvalidTokenStateException):
            self.service.pause(self.tenant.token)
        self.chain.send_transaction.assert_not_called()
