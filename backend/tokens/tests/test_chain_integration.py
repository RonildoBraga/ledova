"""The issuer flow against a live Hardhat node; skipped unless the chain-test environment is set.

`make chain-test` from the repository root starts the node, deploys the core contracts and exports the variables.
The chain is never mocked: the end-to-end test runs unpatched, and the crash and resume tests only patch the
backend side (`BaseChainClient.wait_for_receipt` to lose a receipt, `get_token_by_identifier` to hide a lookup,
`_complete_issuance` to kill the worker) so that every transaction, receipt and read still comes from the node.
"""

import os
import secrets
import threading
import time
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.utils import timezone
from eth_account import Account
from rest_framework.test import APITestCase, APITransactionTestCase

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from companies.models import Company, CompanyStatus
from integrations.base_chain.client import BaseChainClient, get_base_chain_client
from integrations.base_chain.exceptions import BaseChainTransactionError
from shared.tests.tenants import make_tenant
from tokens.exceptions import IssuanceRefusedException, TokenDeploymentFailedException
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
)
from tokens.services import ShareTokenService
from tokens.services.share_token_service import (
    CAP_NOT_RAISED,
    EXCEEDS_AUTHORIZED,
    NOT_WHITELISTED,
    TOKEN_PAUSED,
)
from tokens.tasks import (
    check_executing_issuance_requests,
    check_pending_token_deployments,
    deploy_share_token_task,
    execute_review_request_task,
)
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet
from whitelist.services import WhitelistService

CHAIN_ENV = (
    "CHAIN_TEST_RPC_URL",
    "WHITELIST_CONTRACT_ADDRESS",
    "SHARE_TOKEN_FACTORY_ADDRESS",
    "STABLECOIN_CONTRACT_ADDRESS",
    "ATOMIC_SWAP_ADDRESS",
    "BLOCKCHAIN_OPERATOR_KEY",
)
CHAIN_SETTINGS = {
    "BLOCKCHAIN_RPC_URL": os.environ.get("CHAIN_TEST_RPC_URL", ""),
    "BLOCKCHAIN_CHAIN_ID": 31337,
    **{name: os.environ.get(name, "") for name in CHAIN_ENV[1:]},
}
CAP = 1000


chain_available = skipUnless(
    all(os.environ.get(name) for name in CHAIN_ENV), "CHAIN_TEST_RPC_URL and the core contract addresses"
)


class ChainTestMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        get_base_chain_client.cache_clear()
        BaseChainClient._instance = None
        BaseChainClient._web3 = None

    def setUp(self):
        self.tenant = make_tenant("chain")
        Company.objects.filter(pk=self.tenant.company.pk).update(
            status=CompanyStatus.ACTIVE, acn=f"{secrets.randbelow(10**9):09d}"
        )
        self.token = ShareToken.objects.select_related("company").get(pk=self.tenant.token.pk)
        self.token.total_supply = str(CAP)
        self.token.save(update_fields=["total_supply"])
        self.service = ShareTokenService()
        self.w3 = self.service.chain_client.w3
        snapshot = self.w3.provider.make_request("evm_snapshot", [])["result"]
        self.addCleanup(self.w3.provider.make_request, "evm_revert", [snapshot])
        self.staff = make_tenant("chain-staff", staff=True).user
        self.investor = Account.create().address
        Wallet.objects.create(
            user_account=self.tenant.account,
            address=self.investor,
            chain="base",
            verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
        )

    def _contract(self):
        return self.service.load_share_token(self.token.contract_address)

    @property
    def identifier(self):
        return f"{self.token.company.acn}:{self.token.symbol}"

    def _signer_nonce(self):
        """Transactions sent by the operator so far, whether mined or still in the mempool."""
        signer = self.service.chain_client.get_address_from_private_key(self.service.signer_key)
        return self.w3.eth.get_transaction_count(signer, "pending")

    def _deploy_records(self):
        return BlockchainTransaction.objects.filter(
            tx_type=TransactionType.SHARE_TOKEN_DEPLOY, related_uuid=self.token.uuid
        )

    @staticmethod
    def _crash_after_send():
        """The worker dies right after the create transaction is sent, before its receipt arrives."""

        def crash(client, tx_hash, timeout=120):
            raise BaseChainTransactionError("worker crashed after send")

        return patch.object(BaseChainClient, "wait_for_receipt", crash)

    @staticmethod
    def _lost_receipt():
        """The RPC drops the receipt call after the transaction mined."""
        real = BaseChainClient.wait_for_receipt

        def lose(client, tx_hash, timeout=120):
            real(client, tx_hash, timeout=timeout)
            raise BaseChainTransactionError("receipt lost after the transaction mined")

        return patch.object(BaseChainClient, "wait_for_receipt", lose)

    def _deployed(self):
        self.token.mark_deploying()
        result = deploy_share_token_task(token_uuid=str(self.token.uuid))
        self.assertTrue(result["success"], result)
        self.token.refresh_from_db()
        return result

    def _whitelisted_request(self, amount):
        WhitelistService().add_to_whitelist(self.investor)
        return self._issuance_request(amount)

    def _issuance_request(self, amount):
        return ShareIssuanceRequest.objects.create(
            token=self.token,
            recipient_address=self.investor,
            recipient_name="Investor",
            amount=amount,
            reason="Allotment",
            status=RequestStatus.APPROVED,
            submitted_by=self.tenant.user,
            reviewed_by=self.staff,
        )

    def _execute(self, request):
        return execute_review_request_task(
            model_label=request._meta.label, request_uuid=str(request.uuid), executed_by=self.staff.pk
        )

    def _increase(self, additional):
        return CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=additional,
            new_authorized_total=CAP + additional,
            purpose="Growth",
            board_resolution_reference=f"BOARD-{additional}",
            status=RequestStatus.APPROVED,
        )


@chain_available
@override_settings(**CHAIN_SETTINGS)
class ShareTokenChainTest(ChainTestMixin, APITestCase):
    def test_deploy_whitelist_issue_increase_pause_and_redeploy(self):
        self.token.mark_deploying()
        result = deploy_share_token_task(token_uuid=str(self.token.uuid))
        self.token.refresh_from_db()
        contract_address = result["contract_address"]

        self.assertEqual(result["success"], True)
        self.assertEqual(result["adopted"], False)
        self.assertEqual(result["identifier"], self.identifier)
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.token.contract_address, contract_address)
        self.assertTrue(self.token.deployment_tx_hash.startswith("0x"), self.token.deployment_tx_hash)
        self.assertEqual(self.token.deployment_transaction.tx_hash, self.token.deployment_tx_hash)
        self.assertEqual(self.token.deployment_transaction.status, TransactionStatus.CONFIRMED)
        self.assertTrue(self.token.deployment_transaction.block_hash.startswith("0x"))
        self.assertEqual(self.token.deployment_transaction.function_name, "createShareToken")
        self.assertEqual(self.token.deployment_transaction.function_args["issuerWallet"], self.tenant.wallet.address)
        self.assertEqual(self.service.get_token_by_identifier(self.identifier), contract_address)
        self.assertEqual(self._contract().functions.totalSupply().call(), 0)
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP)
        self.assertFalse(ShareIssuance.objects.filter(token=self.token).exists())

        not_whitelisted = self._issuance_request(amount=10)
        blocks_before = self.w3.eth.block_number
        self.assertEqual(self._execute(not_whitelisted), {"success": False, "error": NOT_WHITELISTED})
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        not_whitelisted.refresh_from_db()
        self.assertEqual(not_whitelisted.status, RequestStatus.APPROVED)
        self.assertEqual(not_whitelisted.review_notes, f"Execution refused: {NOT_WHITELISTED}")

        whitelist = WhitelistService()
        tx_hash, entry = whitelist.add_to_whitelist(self.investor)
        self.assertTrue(tx_hash)
        self.assertTrue(whitelist.is_whitelisted(self.investor))
        self.assertTrue(entry.is_whitelisted)

        too_many = self._issuance_request(amount=CAP + 1)
        blocks_before = self.w3.eth.block_number
        with self.assertRaisesMessage(IssuanceRefusedException, EXCEEDS_AUTHORIZED):
            self.service.execute_request(too_many, executed_by=self.staff)
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        too_many.refresh_from_db()
        self.assertEqual(too_many.status, RequestStatus.APPROVED)
        self.assertEqual(too_many.review_notes, f"Execution refused: {EXCEEDS_AUTHORIZED}")
        self.assertFalse(ShareIssuance.objects.filter(token=self.token).exists())

        executed = self._execute(not_whitelisted)
        self.assertTrue(executed["success"], executed)
        not_whitelisted.refresh_from_db()
        issuance = not_whitelisted.executed_issuance
        self.assertEqual(not_whitelisted.status, RequestStatus.EXECUTED)
        self.assertEqual(issuance.status, IssuanceStatus.COMPLETED)
        self.assertEqual(issuance.initiated_by, self.staff)
        self.assertEqual(issuance.tx_hash, executed["tx_hash"])
        self.assertTrue(issuance.tx_hash.startswith("0x"), issuance.tx_hash)
        self.assertEqual(self.w3.eth.get_transaction_receipt(issuance.tx_hash)["status"], 1)
        self.assertEqual(issuance.block_number, executed["block_number"])
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 10)
        self.assertEqual(self._contract().functions.totalSupply().call(), 10)
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 10)
        self.token.refresh_from_db()
        self.assertEqual(self.token.total_supply, str(CAP))

        self.client.force_authenticate(self.tenant.user)
        holders = self.client.get(f"/api/v1/tokens/{self.token.uuid}/holders/")
        self.assertEqual(holders.status_code, 200)
        self.assertEqual(holders.json()["totalHolders"], 1)
        self.assertEqual(
            holders.json()["holders"][0],
            {
                "address": self.investor,
                "name": "Investor",
                "balance": "10",
                "source": "blockchain",
                "percentage": 100.0,
            },
        )
        self.assertEqual(holders.json()["token"]["totalSupply"], str(CAP))

        increase = CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=500,
            new_authorized_total=CAP + 500,
            purpose="Growth",
            board_resolution_reference="BOARD-1",
            status=RequestStatus.APPROVED,
        )
        increased = self._execute(increase)
        self.assertTrue(increased["success"], increased)
        self.assertEqual(increased["new_authorized_total"], CAP + 500)
        increase.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(increase.status, RequestStatus.EXECUTED)
        self.assertIsNone(increase.executed_issuance)
        self.assertEqual(self.token.total_supply, str(CAP + 500))
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP + 500)
        self.assertEqual(self._contract().functions.totalSupply().call(), 10)

        stale = CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=10,
            new_authorized_total=CAP + 10,
            purpose="Approved against the old cap",
            board_resolution_reference="BOARD-0",
            status=RequestStatus.APPROVED,
        )
        blocks_before = self.w3.eth.block_number
        self.assertEqual(self._execute(stale), {"success": False, "error": CAP_NOT_RAISED})
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        stale.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(
            (stale.status, stale.review_notes), (RequestStatus.APPROVED, f"Execution refused: {CAP_NOT_RAISED}")
        )
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP + 500)
        self.assertEqual(self.token.total_supply, str(CAP + 500))

        self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.PAUSED)
        self.assertTrue(self._contract().functions.paused().call())
        while_paused = self._issuance_request(amount=1)
        blocks_before = self.w3.eth.block_number
        self.assertEqual(self._execute(while_paused), {"success": False, "error": TOKEN_PAUSED})
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        while_paused.refresh_from_db()
        self.assertEqual(
            (while_paused.status, while_paused.review_notes),
            (RequestStatus.APPROVED, f"Execution refused: {TOKEN_PAUSED}"),
        )
        self.assertEqual(ShareIssuance.objects.filter(token=self.token).count(), 1)
        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertFalse(self._contract().functions.paused().call())
        self.assertTrue(self._execute(while_paused)["success"])
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 11)

        self.token.mark_deploying()
        blocks_before = self.w3.eth.block_number
        rerun = deploy_share_token_task(token_uuid=str(self.token.uuid))
        self.token.refresh_from_db()
        self.assertEqual(rerun["success"], True)
        self.assertEqual(rerun["adopted"], True)
        self.assertEqual(rerun["contract_address"], contract_address)
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.token.contract_address, contract_address)
        self.assertEqual(self.w3.eth.block_number, blocks_before)

    def test_crash_after_send_keeps_the_token_deploying_until_the_sweep_binds_it(self):
        nonce_before = self._signer_nonce()
        self.token.mark_deploying()
        with self._crash_after_send():
            with self.assertRaisesMessage(TokenDeploymentFailedException, "worker crashed after send"):
                deploy_share_token_task(token_uuid=str(self.token.uuid))

        self.token.refresh_from_db()
        record = self._deploy_records().get()
        created = self.service.get_token_by_identifier(self.identifier)
        self.assertIsNotNone(created)
        self.assertEqual((self.token.status, self.token.contract_address), (ShareTokenStatus.DEPLOYING, None))
        self.assertEqual((self.token.deployment_tx_hash, self.token.deployment_transaction), (record.tx_hash, record))
        self.assertEqual((record.status, record.error_message), (TransactionStatus.FAILED, "worker crashed after send"))
        self.assertEqual(self._signer_nonce(), nonce_before + 1)

        with patch.object(ShareTokenService, "get_token_by_identifier", side_effect=ConnectionError("rpc down")):
            with self.assertRaisesMessage(TokenDeploymentFailedException, "rpc down"):
                deploy_share_token_task(token_uuid=str(self.token.uuid))
        self.token.refresh_from_db()
        self.assertEqual(
            (self.token.status, self.token.deployment_tx_hash), (ShareTokenStatus.DEPLOYING, record.tx_hash)
        )
        self.assertEqual(self._signer_nonce(), nonce_before + 1)

        self.assertEqual(check_pending_token_deployments(), {"checked": 0, "resolved": 0})
        ShareToken.objects.filter(pk=self.token.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(check_pending_token_deployments(), {"checked": 1, "resolved": 1})
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self.token.contract_address), (ShareTokenStatus.DEPLOYED, created))
        self.assertEqual(self.token.deployment_tx_hash, record.tx_hash)
        self.assertEqual(self._deploy_records().count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.status, TransactionStatus.CONFIRMED)
        self.assertEqual(record.block_number, self.w3.eth.get_transaction_receipt(record.tx_hash)["blockNumber"])
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP)
        self.assertEqual(self._contract().functions.totalSupply().call(), 0)

    def test_retry_resumes_on_the_recorded_transaction_instead_of_sending_again(self):
        rpc = self.w3.provider.make_request

        def restore_mining():
            rpc("evm_setAutomine", [True])
            rpc("evm_mine", [])

        self.addCleanup(restore_mining)
        rpc("evm_setAutomine", [False])
        nonce_before = self._signer_nonce()
        self.token.mark_deploying()
        with self._crash_after_send():
            with self.assertRaises(TokenDeploymentFailedException):
                deploy_share_token_task(token_uuid=str(self.token.uuid))

        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYING)
        self.assertIsNone(self.service.get_token_by_identifier(self.identifier))
        self.assertIsNone(self.service.chain_client.get_transaction_receipt(self.token.deployment_tx_hash))
        self.assertEqual(self._signer_nonce(), nonce_before + 1)

        restore_mining()
        self.assertIsNotNone(self.service.get_token_by_identifier(self.identifier))
        with patch.object(ShareTokenService, "get_token_by_identifier", return_value=None):
            resumed = deploy_share_token_task(token_uuid=str(self.token.uuid))

        self.token.refresh_from_db()
        record = self._deploy_records().get()
        self.assertEqual((resumed["success"], resumed["adopted"]), (True, False))
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.token.contract_address, resumed["contract_address"])
        self.assertEqual(self.service.get_token_by_identifier(self.identifier), self.token.contract_address)
        self.assertEqual(self.token.deployment_tx_hash, record.tx_hash)
        self.assertEqual(record.status, TransactionStatus.CONFIRMED)
        self.assertEqual(record.block_number, self.w3.eth.get_transaction_receipt(record.tx_hash)["blockNumber"])
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP)
        self.assertEqual(self._contract().functions.totalSupply().call(), 0)

    def test_lost_mint_receipt_is_resumed_on_retry_instead_of_minted_again(self):
        self._deployed()
        request = self._whitelisted_request(amount=10)

        with self._lost_receipt():
            with self.assertRaisesMessage(BaseChainTransactionError, "receipt lost after the transaction mined"):
                self._execute(request)

        request.refresh_from_db()
        issuance = ShareIssuance.objects.get(token=self.token)
        self.assertEqual(request.status, RequestStatus.FAILED)
        self.assertTrue(request.can_be_executed)
        self.assertEqual(
            (issuance.status, issuance.idempotency_key), (IssuanceStatus.FAILED, f"issuance-request:{request.uuid}")
        )
        self.assertTrue(issuance.tx_hash.startswith("0x"), issuance.tx_hash)
        self.assertEqual(self.w3.eth.get_transaction_receipt(issuance.tx_hash)["status"], 1)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 10)
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 0)

        nonce_before = self._signer_nonce()
        with patch.object(BaseChainClient, "wait_for_receipt", side_effect=AssertionError("nothing to wait for")):
            retried = self._execute(request)

        self.assertTrue(retried["success"], retried)
        self.assertEqual(retried["tx_hash"], issuance.tx_hash)
        self.assertEqual(self._signer_nonce(), nonce_before)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 10)
        self.assertEqual(self._contract().functions.totalSupply().call(), 10)
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual(list(ShareIssuance.objects.filter(token=self.token)), [issuance])
        self.assertEqual((issuance.status, issuance.block_number), (IssuanceStatus.COMPLETED, retried["block_number"]))
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, issuance))
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 10)

    def test_lost_set_authorized_receipt_is_resumed_on_retry_instead_of_refusing_the_increase(self):
        self._deployed()
        increase = self._increase(500)

        with self._lost_receipt():
            with self.assertRaisesMessage(TokenDeploymentFailedException, "receipt lost after the transaction mined"):
                self._execute(increase)

        increase.refresh_from_db()
        self.token.refresh_from_db()
        record = BlockchainTransaction.objects.get(
            related_model="tokens.CapitalIncreaseRequest", related_uuid=increase.uuid
        )
        self.assertEqual((increase.status, self.token.total_supply), (RequestStatus.FAILED, str(CAP)))
        self.assertTrue(increase.can_be_executed)
        self.assertEqual((record.status, record.function_name), (TransactionStatus.FAILED, "setAuthorizedShares"))
        self.assertTrue(record.tx_hash.startswith("0x"), record.tx_hash)
        self.assertEqual(self.w3.eth.get_transaction_receipt(record.tx_hash)["status"], 1)
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP + 500)

        nonce_before = self._signer_nonce()
        with patch.object(BaseChainClient, "wait_for_receipt", side_effect=AssertionError("nothing to wait for")):
            retried = self._execute(increase)

        self.assertTrue(retried["success"], retried)
        self.assertEqual((retried["tx_hash"], retried["new_authorized_total"]), (record.tx_hash, CAP + 500))
        self.assertEqual(self._signer_nonce(), nonce_before)
        increase.refresh_from_db()
        record.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((increase.status, increase.executed_issuance), (RequestStatus.EXECUTED, None))
        self.assertEqual(self.token.total_supply, str(CAP + 500))
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP + 500)
        self.assertEqual((record.status, record.block_number), (TransactionStatus.CONFIRMED, retried["block_number"]))
        self.assertEqual(BlockchainTransaction.objects.filter(related_model="tokens.CapitalIncreaseRequest").count(), 1)

        again = self._increase(600)
        self.assertTrue(self._execute(again)["success"])
        self.token.refresh_from_db()
        self.assertEqual(self.token.total_supply, str(CAP + 600))
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP + 600)

    def test_lost_pause_receipt_and_an_outside_pause_are_reconciled_instead_of_stranding_the_token(self):
        self._deployed()
        contract = self._contract()

        with self._lost_receipt():
            self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.PAUSED)
        self.assertTrue(contract.functions.paused().call())

        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertFalse(contract.functions.paused().call())

        self.service.chain_client.send_transaction(contract.functions.pause(), self.service.signer_key)
        self.assertTrue(contract.functions.paused().call())
        nonce_before = self._signer_nonce()
        self.service.pause(self.token)
        self.token.refresh_from_db()
        self.assertEqual((self.token.status, self._signer_nonce()), (ShareTokenStatus.PAUSED, nonce_before))

        ShareToken.objects.filter(pk=self.token.pk).update(status=ShareTokenStatus.DEPLOYED)
        self.token.refresh_from_db()
        request = self._whitelisted_request(amount=5)
        blocks_before = self.w3.eth.block_number
        self.assertEqual(self._execute(request), {"success": False, "error": TOKEN_PAUSED})
        self.assertEqual(self.w3.eth.block_number, blocks_before)
        self.service.unpause(self.token)
        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertFalse(contract.functions.paused().call())

        self.assertTrue(self._execute(request)["success"])
        self.assertEqual(contract.functions.balanceOf(self.investor).call(), 5)

    def test_worker_killed_after_the_mint_is_finished_by_the_executing_sweep(self):
        self._deployed()
        request = self._whitelisted_request(amount=10)

        with patch.object(ShareTokenService, "_complete_issuance", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._execute(request)

        request.refresh_from_db()
        issuance = ShareIssuance.objects.get(token=self.token)
        self.assertEqual((request.status, issuance.status), (RequestStatus.EXECUTING, IssuanceStatus.PROCESSING))
        self.assertFalse(request.can_be_executed)
        self.assertTrue(issuance.tx_hash.startswith("0x"), issuance.tx_hash)
        self.assertEqual(self._contract().functions.balanceOf(self.investor).call(), 10)
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 0)

        self.assertEqual(check_executing_issuance_requests(), {"checked": 0, "resolved": 0})
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        nonce_before = self._signer_nonce()
        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 1})

        self.assertEqual(self._signer_nonce(), nonce_before)
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual(list(ShareIssuance.objects.filter(token=self.token)), [issuance])
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, issuance))
        self.assertEqual(issuance.status, IssuanceStatus.COMPLETED)
        self.assertEqual(issuance.block_number, self.w3.eth.get_transaction_receipt(issuance.tx_hash)["blockNumber"])
        self.assertEqual(self._contract().functions.totalSupply().call(), 10)
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 10)


@chain_available
@override_settings(**CHAIN_SETTINGS)
class ShareTokenChainConcurrencyTest(ChainTestMixin, APITransactionTestCase):
    """Two workers executing two approved increases in one block window; needs a database that honours row locks."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("select_for_update is a no-op on SQLite")
        super().setUp()

    def _wait_until(self, condition, timeout=15):
        deadline = time.monotonic() + timeout
        while not condition():
            self.assertLess(time.monotonic(), deadline, "timed out waiting on the chain")
            time.sleep(0.05)

    def test_two_increases_executed_in_one_block_window_cannot_lower_the_cap(self):
        """'big' (+1000) sends and waits unmined while 'small' (+50) blocks on the token row until 'big' commits."""
        self._deployed()
        big = self._increase(1000)
        small = self._increase(50)
        rpc = self.w3.provider.make_request

        def restore_mining():
            rpc("evm_setAutomine", [True])
            rpc("evm_mine", [])

        self.addCleanup(restore_mining)
        rpc("evm_setAutomine", [False])
        nonce_before = self._signer_nonce()
        results = {}

        def worker(name, request):
            try:
                results[name] = self._execute(request)
            except Exception as exc:
                results[name] = exc
            finally:
                connection.close()

        first = threading.Thread(target=worker, args=("big", big))
        second = threading.Thread(target=worker, args=("small", small))
        first.start()
        self._wait_until(lambda: self._signer_nonce() == nonce_before + 1)
        second.start()
        time.sleep(1)
        self.assertEqual(self._signer_nonce(), nonce_before + 1)
        self.assertEqual(results, {})
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP)

        rpc("evm_mine", [])
        first.join(timeout=60)
        second.join(timeout=60)
        self.assertFalse(first.is_alive() or second.is_alive(), results)

        self.assertIsInstance(results["big"], dict, results)
        self.assertTrue(results["big"]["success"], results)
        self.assertEqual(results["small"], {"success": False, "error": CAP_NOT_RAISED})
        self.assertEqual(self._signer_nonce(), nonce_before + 1)
        self.assertEqual(self._contract().functions.authorizedShares().call(), CAP + 1000)
        big.refresh_from_db()
        small.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((big.status, small.status), (RequestStatus.EXECUTED, RequestStatus.APPROVED))
        self.assertEqual(small.review_notes, f"Execution refused: {CAP_NOT_RAISED}")
        self.assertEqual(self.token.total_supply, str(CAP + 1000))
