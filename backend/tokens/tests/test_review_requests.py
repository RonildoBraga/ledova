"""The shared review workflow: model transitions, dilution, the status data migration, execute_request and its task."""

import importlib
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from web3 import Web3

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from shared.tests.tenants import make_tenant
from tokens.exceptions import (
    InvalidRecipientAddressException,
    InvalidTokenStateException,
    IssuanceRefusedException,
    TokenDeploymentFailedException,
)
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
)
from tokens.serializers import CapitalIncreaseDetailSerializer
from tokens.services import ShareTokenService
from tokens.services.share_token_service import (
    CAP_NOT_RAISED,
    EXCEEDS_AUTHORIZED,
    NOT_WHITELISTED,
    TOKEN_PAUSED,
)
from tokens.tasks import check_executing_issuance_requests, execute_review_request_task

RECIPIENT = "0x" + "a" * 40
SIGNER = "0x" + "e" * 40
RECEIPT = {"blockNumber": 9, "blockHash": bytes.fromhex("ab" * 32), "gasUsed": 1_000_000}
CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
WHITELISTED = "tokens.services.share_token_service.ShareTokenService.is_recipient_whitelisted"
SUPPLY = "tokens.services.share_token_service.ShareTokenService.share_supply"


def issuance_request(token, amount=10, **fields):
    return ShareIssuanceRequest.objects.create(
        token=token, recipient_address=RECIPIENT, recipient_name="Alice", amount=amount, reason="Bonus", **fields
    )


class ReviewableRequestModelTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token

    def test_completed_supply_feeds_dilution_for_both_request_types(self):
        self.assertEqual(self.tenant.capital_increase.calculate_dilution(), 0.0)
        ShareIssuance.objects.create(token=self.token, recipient_address=RECIPIENT, amount="900", status="completed")
        ShareIssuance.objects.create(token=self.token, recipient_address=RECIPIENT, amount="500", status="pending")

        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 900)
        self.assertEqual(self.tenant.capital_increase.calculate_dilution(), 10.0)
        self.assertEqual(issuance_request(self.token, amount=100).calculate_dilution(), 10.0)

    def test_capital_increase_walks_submit_review_approve_execute_fail(self):
        request = self.tenant.capital_increase
        self.assertTrue(request.can_be_edited and request.can_be_submitted)
        self.assertFalse(request.can_be_approved)
        with self.assertRaises(ValueError):
            request.approve(self.tenant.user)

        request.submit(self.tenant.user)
        self.assertEqual(
            (request.status, request.submitted_by, request.dilution_percentage), ("submitted", self.tenant.user, 0.0)
        )
        self.assertFalse(request.can_be_edited)

        request.start_review(self.tenant.user)
        request.approve(self.tenant.user, notes="ok")
        self.assertEqual((request.status, request.review_notes), (RequestStatus.APPROVED, "ok"))
        self.assertIsNotNone(request.reviewed_at)
        self.assertTrue(request.can_be_executed)

        request.mark_executing()
        self.assertFalse(request.can_be_executed)
        request.mark_failed("boom")
        self.assertEqual((request.status, request.review_notes), (RequestStatus.FAILED, "Execution failed: boom"))
        self.assertTrue(request.can_be_executed)
        with self.assertRaises(ValueError):
            request.reject(self.tenant.user, reason="too late")

    def test_mark_executing_claims_the_row_once(self):
        request = self.tenant.capital_increase
        CapitalIncreaseRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        request.refresh_from_db()
        stale = CapitalIncreaseRequest.objects.get(pk=request.pk)

        request.mark_executing()
        self.assertEqual(request.status, RequestStatus.EXECUTING)
        self.assertTrue(stale.can_be_executed)
        with self.assertRaisesMessage(ValueError, "Cannot execute request with status 'Executing'"):
            stale.mark_executing()
        self.assertEqual(stale.status, RequestStatus.EXECUTING)
        self.assertEqual(CapitalIncreaseRequest.objects.get(pk=request.pk).status, RequestStatus.EXECUTING)

    def test_issuance_request_starts_submitted_and_can_be_rejected(self):
        request = issuance_request(self.token)
        self.assertEqual(request.status, RequestStatus.SUBMITTED)
        request.start_review(self.tenant.user)
        request.reject(self.tenant.user, reason="Not now")
        self.assertEqual((request.status, request.rejection_reason), (RequestStatus.REJECTED, "Not now"))
        with self.assertRaises(ValueError):
            request.mark_executing()

    def test_detail_serializer_keeps_the_keys_the_dashboard_reads(self):
        data = CapitalIncreaseDetailSerializer(self.tenant.capital_increase).data
        self.assertEqual(data["status"], "draft")
        self.assertTrue(data["can_be_edited"] and data["can_be_submitted"])
        self.assertIsNone(data["dilution_percentage"])


class StatusDataMigrationTest(TestCase):
    def test_pending_approval_maps_to_submitted_and_back(self):
        migration = importlib.import_module("tokens.migrations.0012_reviewable_request")
        tenant = make_tenant("owner")
        request = issuance_request(tenant.deployed_token)
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status="pending_approval")
        tenant.capital_increase.submit(tenant.user)

        migration.forwards(apps, None)
        request.refresh_from_db()
        self.assertEqual(request.status, "submitted")

        migration.backwards(apps, None)
        request.refresh_from_db()
        tenant.capital_increase.refresh_from_db()
        self.assertEqual(request.status, "pending_approval")
        self.assertEqual(tenant.capital_increase.status, "submitted")


@override_settings(BLOCKCHAIN_OPERATOR_KEY="0xkey")
class ExecuteRequestServiceTest(TestCase):
    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.chain.is_valid_address.return_value = True
        self.chain.to_checksum_address.side_effect = Web3.to_checksum_address
        self.chain.get_address_from_private_key.return_value = SIGNER
        self._chain_paused(False)
        patch(WHITELISTED, return_value=True).start()
        patch(SUPPLY, return_value=(1000, 0)).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token
        self.service = ShareTokenService()

    def _approved(self, request):
        type(request).objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        request.refresh_from_db()
        return request

    def _chain_paused(self, value):
        self.chain.load_contract.return_value.functions.paused.return_value.call.return_value = value

    def _token_status(self, status):
        ShareToken.objects.filter(pk=self.token.pk).update(status=status)
        self.token.refresh_from_db()

    def _set_authorized_contract(self):
        """The chain answers a setAuthorizedShares send with 0xset and its receipt on the wait."""
        self.chain.send_transaction.return_value = ("0xset", None)
        self.chain.wait_for_receipt.return_value = {
            "blockNumber": 5,
            "blockHash": bytes.fromhex("cd" * 32),
            "gasUsed": 30000,
        }
        self.chain.get_transaction_receipt.return_value = None
        return self.chain.load_contract.return_value

    def _increase_records(self, request):
        return BlockchainTransaction.objects.filter(
            related_model="tokens.CapitalIncreaseRequest", related_uuid=request.uuid
        ).order_by("created_at")

    def _recorded_increase(self, request, tx_hash="0xold", status=TransactionStatus.FAILED):
        return BlockchainTransaction.objects.create(
            tx_type=TransactionType.OTHER,
            status=status,
            tx_hash=tx_hash,
            from_address=SIGNER,
            to_address=self.token.contract_address,
            function_name="setAuthorizedShares",
            related_model="tokens.CapitalIncreaseRequest",
            related_uuid=request.uuid,
        )

    def test_capital_increase_sets_the_validated_cap_and_mints_nothing(self):
        request = self._approved(self.tenant.capital_increase)
        chain_result = {"tx_hash": "0xset", "block_number": 5, "gas_used": 21000, "new_authorized_total": 1100}
        with patch.object(ShareTokenService, "increase_authorized_shares", return_value=chain_result) as increase:
            with patch.object(ShareTokenService, "_mint_to") as mint:
                result = self.service.execute_request(request)

        self.assertEqual(result, chain_result)
        increase.assert_called_once_with(request)
        mint.assert_not_called()
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, None))
        self.assertIsNotNone(request.executed_at)
        self.assertEqual(self.token.total_supply, "1100")
        self.assertFalse(ShareIssuance.objects.exists())

    def test_capital_increase_not_above_the_chain_cap_is_refused_before_any_transaction(self):
        """Two increases approved against one cap: once the first ran, the second would lower the cap."""
        request = self._approved(self.tenant.capital_increase)
        CapitalIncreaseRequest.objects.filter(pk=request.pk).update(new_authorized_total=1200)
        request.refresh_from_db()
        for authorized in (1500, 1201):
            with self.subTest(authorized=authorized):
                with patch(SUPPLY, return_value=(authorized, 10)):
                    with self.assertRaisesMessage(IssuanceRefusedException, CAP_NOT_RAISED):
                        self.service.execute_request(request)

        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, request.executed_at), (RequestStatus.APPROVED, None))
        self.assertTrue(request.can_be_executed)
        self.assertEqual(request.review_notes, f"Execution refused: {CAP_NOT_RAISED}")
        self.assertEqual(self.token.total_supply, "1000")

        contract = self._set_authorized_contract()
        with patch(SUPPLY, return_value=(1199, 10)):
            result = self.service.execute_request(request)
        self.assertEqual(
            result, {"tx_hash": "0xset", "block_number": 5, "gas_used": 30000, "new_authorized_total": 1200}
        )
        contract.functions.setAuthorizedShares.assert_called_once_with(1200)
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, self.token.total_supply), (RequestStatus.EXECUTED, "1200"))
        record = self._increase_records(request).get()
        self.assertEqual(
            (record.status, record.tx_hash, record.block_number), (TransactionStatus.CONFIRMED, "0xset", 5)
        )
        self.assertEqual((record.tx_type, record.function_name), (TransactionType.OTHER, "setAuthorizedShares"))
        self.assertEqual((record.from_address, record.to_address), (SIGNER, self.token.contract_address))
        self.assertEqual(record.function_args, {"newAuthorizedShares": "1200"})
        self.assertEqual(record.block_hash, "0x" + "cd" * 32)

    def test_a_chain_cap_equal_to_the_request_with_the_db_cap_behind_is_adopted_instead_of_refused(self):
        """A worker killed between the send and the hash write: nothing recorded, the chain already at the cap."""
        request = self._approved(self.tenant.capital_increase)
        self._set_authorized_contract()
        with patch(SUPPLY, return_value=(1100, 0)):
            with self.assertLogs("tokens.services.share_token_service", "WARNING") as logs:
                result = self.service.execute_request(request)

        self.assertEqual(result["adopted"], True)
        self.assertEqual((result["tx_hash"], result["new_authorized_total"]), (None, 1100))
        self.assertIn("adopting the chain cap", logs.output[0])
        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, None))
        self.assertIsNotNone(request.executed_at)
        self.assertEqual(self.token.total_supply, "1100")
        self.assertFalse(self._increase_records(request).exists())

        # The DB cap already there means a genuinely stale request: still refused.
        stale = self._approved(self.tenant.capital_increase)
        CapitalIncreaseRequest.objects.filter(pk=stale.pk).update(status=RequestStatus.APPROVED)
        stale.refresh_from_db()
        with patch(SUPPLY, return_value=(1100, 0)):
            with self.assertRaisesMessage(IssuanceRefusedException, CAP_NOT_RAISED):
                self.service.execute_request(stale)

    def test_retry_resumes_on_a_confirmed_record_whose_completion_writes_were_lost(self):
        request = self._approved(self.tenant.capital_increase)
        request.mark_failed("worker died after the receipt")
        confirmed = self._recorded_increase(request, tx_hash="0xdone", status=TransactionStatus.CONFIRMED)
        self._set_authorized_contract()
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}

        result = self.service.execute_request(request)

        self.assertEqual(result["tx_hash"], "0xdone")
        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        self.token.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual((request.status, self.token.total_supply), (RequestStatus.EXECUTED, "1100"))
        self.assertEqual(confirmed.status, TransactionStatus.CONFIRMED)
        self.assertEqual(self._increase_records(request).count(), 1)

    def test_capital_increase_holds_a_row_lock_on_the_token_from_the_cap_read_to_the_cap_write(self):
        """Two workers in one block window: the second reads the cap only after the first has committed."""
        if connection.vendor != "postgresql":
            self.skipTest("select_for_update is a no-op on SQLite")
        request = self._approved(self.tenant.capital_increase)
        self._set_authorized_contract()
        with CaptureQueriesContext(connection) as queries:
            self.service.execute_request(request)

        sql = [query["sql"] for query in queries.captured_queries]
        locks = [index for index, statement in enumerate(sql) if "FOR UPDATE" in statement]
        self.assertEqual(len(locks), 1, sql)
        self.assertIn('"tokens_sharetoken"', sql[locks[0]])
        cap_write = next(
            index for index, statement in enumerate(sql) if statement.startswith('UPDATE "tokens_sharetoken"')
        )
        self.assertLess(locks[0], cap_write, sql)
        self.chain.load_contract.return_value.functions.setAuthorizedShares.assert_called_once_with(1100)
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, self.token.total_supply), (RequestStatus.EXECUTED, "1100"))

    def test_a_stale_copy_of_an_executed_request_completes_without_touching_the_chain(self):
        """Loaded before the first executor finished, it finds the completed issuance and mints nothing."""
        request = self._approved(issuance_request(self.token, amount=10))
        stale = ShareIssuanceRequest.objects.get(pk=request.pk)
        self.chain.send_transaction.return_value = ("0xmint", None)
        self.chain.wait_for_receipt.return_value = RECEIPT
        first = self.service.execute_request(request)
        request.refresh_from_db()
        self.chain.send_transaction.reset_mock()
        self.chain.get_transaction_receipt.side_effect = AssertionError("nothing to read")
        self.chain.wait_for_receipt.side_effect = AssertionError("nothing to wait for")

        self.assertTrue(stale.can_be_executed)
        self.assertEqual(self.service.execute_request(stale), first)

        self.chain.send_transaction.assert_not_called()
        stale.refresh_from_db()
        self.assertEqual((stale.status, stale.executed_at), (RequestStatus.EXECUTED, request.executed_at))
        self.assertEqual(ShareIssuance.objects.filter(token=self.token).count(), 1)

    def test_issuance_on_a_paused_token_is_refused_but_a_capital_increase_proceeds(self):
        self._token_status(ShareTokenStatus.PAUSED)
        request = self._approved(issuance_request(self.token, amount=10))
        with patch.object(ShareTokenService, "_mint_to") as mint:
            with self.assertRaisesMessage(IssuanceRefusedException, TOKEN_PAUSED):
                self.service.execute_request(request)
        mint.assert_not_called()
        request.refresh_from_db()
        self.assertEqual(
            (request.status, request.review_notes), (RequestStatus.APPROVED, f"Execution refused: {TOKEN_PAUSED}")
        )
        self.assertFalse(ShareIssuance.objects.exists())

        increase = self._approved(self.tenant.capital_increase)
        chain_result = {"tx_hash": "0xset", "block_number": 5, "gas_used": 21000, "new_authorized_total": 1100}
        with patch.object(ShareTokenService, "increase_authorized_shares", return_value=chain_result):
            self.assertEqual(self.service.execute_request(increase), chain_result)
        increase.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((increase.status, self.token.status), (RequestStatus.EXECUTED, ShareTokenStatus.PAUSED))
        self.assertEqual(self.token.total_supply, "1100")

        self._token_status(ShareTokenStatus.DEPLOYED)
        self._chain_paused(True)
        request = self._approved(request)
        with patch.object(ShareTokenService, "_mint_to") as mint:
            with self.assertRaisesMessage(IssuanceRefusedException, TOKEN_PAUSED):
                self.service.execute_request(request)
        mint.assert_not_called()
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.APPROVED)

    def test_a_second_executor_loses_the_claim_and_does_not_mint(self):
        """The first worker has created the issuance row but not yet written the mint hash."""
        request = self._approved(issuance_request(self.token, amount=10))
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address=RECIPIENT,
            amount="10",
            status=IssuanceStatus.PROCESSING,
            idempotency_key=ShareTokenService.issuance_key(request),
        )
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTING)
        self.assertTrue(request.can_be_executed)

        with patch.object(ShareTokenService, "_mint_to") as mint:
            with self.assertRaisesMessage(InvalidTokenStateException, "Cannot execute request with status 'Executing'"):
                self.service.execute_request(request)

        mint.assert_not_called()
        self.chain.send_transaction.assert_not_called()
        self.assertEqual(ShareIssuance.objects.filter(token=self.token).count(), 1)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTING)

    def test_increase_authorized_shares_sends_set_authorized_only(self):
        request = self.tenant.capital_increase
        token_contract = self._set_authorized_contract()
        result = self.service.increase_authorized_shares(request)

        token_contract.functions.setAuthorizedShares.assert_called_once_with(1100)
        self.chain.send_transaction.assert_called_once_with(
            token_contract.functions.setAuthorizedShares.return_value, "0xkey", wait_for_receipt=False
        )
        self.chain.wait_for_receipt.assert_called_once_with("0xset")
        token_contract.functions.mint.assert_not_called()
        self.assertEqual(
            result, {"tx_hash": "0xset", "block_number": 5, "gas_used": 30000, "new_authorized_total": 1100}
        )
        self.assertEqual(self._increase_records(request).get().status, TransactionStatus.CONFIRMED)

    def test_set_authorized_hash_is_recorded_before_the_wait_and_a_retry_completes_from_it_without_sending(self):
        """A receipt lost after setAuthorizedShares mined: the chain cap is raised, the DB cap is not yet."""
        request = self._approved(self.tenant.capital_increase)
        self._set_authorized_contract()
        self.chain.wait_for_receipt.side_effect = RuntimeError("rpc timed out after the call mined")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "rpc timed out after the call mined"):
            self.service.execute_request(request)

        self.chain.send_transaction.assert_called_once()
        request.refresh_from_db()
        self.token.refresh_from_db()
        record = self._increase_records(request).get()
        self.assertEqual((request.status, self.token.total_supply), (RequestStatus.FAILED, "1000"))
        self.assertTrue(request.can_be_executed)
        self.assertEqual((record.status, record.tx_hash), (TransactionStatus.FAILED, "0xset"))
        self.assertEqual(record.error_message, "rpc timed out after the call mined")

        self.chain.send_transaction.reset_mock()
        self.chain.wait_for_receipt.reset_mock()
        self.chain.wait_for_receipt.side_effect = None
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}
        with patch(SUPPLY, return_value=(1100, 0)):
            result = self.service.execute_request(request)

        self.assertEqual(
            result, {"tx_hash": "0xset", "block_number": 9, "gas_used": 1_000_000, "new_authorized_total": 1100}
        )
        self.chain.get_transaction_receipt.assert_called_once_with("0xset")
        self.chain.send_transaction.assert_not_called()
        self.chain.wait_for_receipt.assert_not_called()
        request.refresh_from_db()
        self.token.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(self._increase_records(request).count(), 1)
        self.assertEqual((record.status, record.block_number), (TransactionStatus.CONFIRMED, 9))
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, None))
        self.assertIsNotNone(request.executed_at)
        self.assertEqual(self.token.total_supply, "1100")

    def test_retry_on_a_reverted_recorded_call_forgets_it_and_sends_afresh(self):
        request = self._approved(self.tenant.capital_increase)
        request.mark_failed("rpc down")
        old = self._recorded_increase(request)
        contract = self._set_authorized_contract()
        self.chain.get_transaction_receipt.return_value = {"status": 0, **RECEIPT}

        result = self.service.execute_request(request)

        self.assertEqual(result["tx_hash"], "0xset")
        self.chain.get_transaction_receipt.assert_called_once_with("0xold")
        self.chain.send_transaction.assert_called_once()
        contract.functions.setAuthorizedShares.assert_called_once_with(1100)
        old.refresh_from_db()
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((old.status, old.error_message), (TransactionStatus.REVERTED, "Transaction reverted: 0xold"))
        self.assertEqual([r.tx_hash for r in self._increase_records(request)], ["0xold", "0xset"])
        self.assertEqual((request.status, self.token.total_supply), (RequestStatus.EXECUTED, "1100"))

    def test_retry_on_an_unconfirmed_recorded_call_waits_on_it_instead_of_sending(self):
        request = self._approved(self.tenant.capital_increase)
        request.mark_failed("rpc down")
        old = self._recorded_increase(request)
        self._set_authorized_contract()

        self.chain.wait_for_receipt.side_effect = RuntimeError("still pending")
        with self.assertRaisesMessage(TokenDeploymentFailedException, "still pending"):
            self.service.execute_request(request)
        request.refresh_from_db()
        old.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, old.status, old.error_message), ("failed", "failed", "still pending"))
        self.assertEqual(self.token.total_supply, "1000")

        self.chain.wait_for_receipt.side_effect = None
        result = self.service.execute_request(request)
        self.assertEqual(result["tx_hash"], "0xold")
        self.chain.wait_for_receipt.assert_called_with("0xold")
        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        old.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((old.status, request.status, self.token.total_supply), ("confirmed", "executed", "1100"))

    def test_a_resumed_increase_never_lowers_a_cap_a_later_one_raised(self):
        """The first increase lost its receipt, a second (higher) one executed meanwhile, then the first is retried."""
        request = self._approved(self.tenant.capital_increase)
        request.mark_failed("rpc down")
        self._recorded_increase(request)
        self._set_authorized_contract()
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}
        ShareToken.objects.filter(pk=self.token.pk).update(total_supply="1500")

        self.assertEqual(self.service.execute_request(request)["tx_hash"], "0xold")

        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, self.token.total_supply), (RequestStatus.EXECUTED, "1500"))

    def test_a_stale_copy_of_an_executed_increase_is_refused_without_touching_its_notes(self):
        request = self._approved(self.tenant.capital_increase)
        stale = CapitalIncreaseRequest.objects.get(pk=request.pk)
        self._set_authorized_contract()
        self.service.execute_request(request)
        request.refresh_from_db()
        self.chain.send_transaction.reset_mock()

        self.assertTrue(stale.can_be_executed)
        with patch(SUPPLY, return_value=(1100, 0)) as supply:
            with self.assertRaisesMessage(InvalidTokenStateException, "Cannot execute request with status 'Executed'"):
                self.service.execute_request(stale)

        supply.assert_not_called()
        self.chain.send_transaction.assert_not_called()
        stale.refresh_from_db()
        self.assertEqual((stale.status, stale.review_notes, stale.executed_at), ("executed", "", request.executed_at))

    def test_issuance_request_mints_to_its_recipient_and_leaves_the_cap(self):
        request = self._approved(issuance_request(self.token, amount=10, reviewed_by=self.tenant.user))
        staff = make_tenant("staff", staff=True).user
        chain_result = {"tx_hash": "0xmint", "block_number": 7, "gas_used": 21000}
        with patch.object(ShareTokenService, "_mint_to", return_value=chain_result) as mint:
            self.assertEqual(self.service.execute_request(request, executed_by=staff), chain_result)

        mint.assert_called_once()
        self.assertEqual(mint.call_args.args, (self.token.contract_address, Web3.to_checksum_address(RECIPIENT), 10))
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        self.assertEqual(self.token.total_supply, "1000")
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 10)
        issuance = request.executed_issuance
        self.assertEqual(issuance.recipient_address, Web3.to_checksum_address(RECIPIENT))
        self.assertEqual(
            (issuance.recipient_name, issuance.issuance_type, issuance.amount), ("Alice", "additional", "10")
        )
        self.assertEqual((issuance.reason, issuance.initiated_by), ("Issuance request: Bonus", staff))
        self.assertEqual((issuance.tx_hash, issuance.block_number), ("0xmint", 7))
        self.assertEqual(issuance.shareissuancerequest, request)

    def test_issuance_without_an_executing_user_credits_the_reviewer(self):
        request = self._approved(issuance_request(self.token, amount=10, reviewed_by=self.tenant.user))
        with patch.object(
            ShareTokenService, "_mint_to", return_value={"tx_hash": "0x1", "block_number": 1, "gas_used": 1}
        ):
            self.service.execute_request(request)
        request.refresh_from_db()
        self.assertEqual(request.executed_issuance.initiated_by, self.tenant.user)

    def test_unwhitelisted_recipient_is_refused_before_any_transaction(self):
        request = self._approved(issuance_request(self.token, amount=10))
        with patch(WHITELISTED, return_value=False):
            with patch.object(ShareTokenService, "_mint_to") as mint:
                with self.assertRaisesMessage(IssuanceRefusedException, NOT_WHITELISTED):
                    self.service.execute_request(request)

        mint.assert_not_called()
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.APPROVED)
        self.assertTrue(request.can_be_executed)
        self.assertEqual(request.review_notes, f"Execution refused: {NOT_WHITELISTED}")
        self.assertFalse(ShareIssuance.objects.exists())

    def test_amount_over_the_remaining_cap_is_refused_before_any_transaction(self):
        request = self._approved(issuance_request(self.token, amount=101))
        with patch(SUPPLY, return_value=(1000, 900)):
            with patch.object(ShareTokenService, "_mint_to") as mint:
                with self.assertRaisesMessage(IssuanceRefusedException, EXCEEDS_AUTHORIZED):
                    self.service.execute_request(request)
            mint.assert_not_called()

            exact = self._approved(issuance_request(self.token, amount=100))
            with patch.object(
                ShareTokenService, "_mint_to", return_value={"tx_hash": "0x1", "block_number": 1, "gas_used": 1}
            ):
                self.service.execute_request(exact)

        request.refresh_from_db()
        exact.refresh_from_db()
        self.assertEqual((request.status, exact.status), (RequestStatus.APPROVED, RequestStatus.EXECUTED))
        self.assertEqual(request.review_notes, f"Execution refused: {EXCEEDS_AUTHORIZED}")

    def test_chain_failure_marks_request_and_issuance_failed_then_reraises(self):
        request = self._approved(issuance_request(self.token))
        with patch.object(ShareTokenService, "_mint_to", side_effect=RuntimeError("rpc down")):
            with self.assertRaisesMessage(RuntimeError, "rpc down"):
                self.service.execute_request(request)

        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, request.review_notes), (RequestStatus.FAILED, "Execution failed: rpc down"))
        self.assertTrue(request.can_be_executed)
        self.assertEqual(self.token.total_supply, "1000")
        issuance = ShareIssuance.objects.get(token=self.token)
        self.assertEqual((issuance.status, issuance.error_message), (IssuanceStatus.FAILED, "rpc down"))
        self.assertEqual(issuance.idempotency_key, f"issuance-request:{request.uuid}")
        self.assertIsNone(request.executed_issuance)

    def _mint_contract(self):
        contract = self.chain.load_contract.return_value
        self.chain.send_transaction.return_value = ("0xmint", None)
        self.chain.wait_for_receipt.return_value = RECEIPT
        self.chain.get_transaction_receipt.return_value = None
        return contract

    def _recorded_issuance(self, request, tx_hash="0xold", status=IssuanceStatus.FAILED):
        return ShareIssuance.objects.create(
            token=self.token,
            recipient_address=RECIPIENT,
            amount=str(request.amount),
            status=status,
            tx_hash=tx_hash,
            idempotency_key=ShareTokenService.issuance_key(request),
        )

    def test_mint_hash_is_recorded_before_the_wait_and_a_retry_completes_from_it_without_minting_again(self):
        request = self._approved(issuance_request(self.token, amount=10))
        contract = self._mint_contract()
        self.chain.wait_for_receipt.side_effect = RuntimeError("rpc timed out after the mint mined")
        with self.assertRaisesMessage(RuntimeError, "rpc timed out after the mint mined"):
            self.service.execute_request(request)

        self.chain.send_transaction.assert_called_once_with(
            contract.functions.mint.return_value, "0xkey", wait_for_receipt=False
        )
        request.refresh_from_db()
        issuance = ShareIssuance.objects.get(token=self.token)
        self.assertEqual(request.status, RequestStatus.FAILED)
        self.assertEqual((issuance.status, issuance.tx_hash), (IssuanceStatus.FAILED, "0xmint"))
        self.assertEqual(issuance.error_message, "rpc timed out after the mint mined")

        self.chain.send_transaction.reset_mock()
        self.chain.wait_for_receipt.reset_mock()
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}
        with patch(SUPPLY, return_value=(1000, 1000)):
            result = self.service.execute_request(request)

        self.assertEqual(result, {"tx_hash": "0xmint", "block_number": 9, "gas_used": 1_000_000})
        self.chain.get_transaction_receipt.assert_called_once_with("0xmint")
        self.chain.send_transaction.assert_not_called()
        self.chain.wait_for_receipt.assert_not_called()
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual(ShareIssuance.objects.filter(token=self.token).count(), 1)
        self.assertEqual((issuance.status, issuance.tx_hash, issuance.block_number), ("completed", "0xmint", 9))
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, issuance))
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 10)

    def test_retry_on_a_reverted_recorded_mint_forgets_it_and_mints_afresh_on_the_same_issuance(self):
        request = self._approved(issuance_request(self.token, amount=10))
        request.mark_failed("rpc down")
        issuance = self._recorded_issuance(request)
        self._mint_contract()
        self.chain.get_transaction_receipt.return_value = {"status": 0, **RECEIPT}

        result = self.service.execute_request(request)

        self.assertEqual(result["tx_hash"], "0xmint")
        self.chain.send_transaction.assert_called_once()
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual(ShareIssuance.objects.filter(token=self.token).count(), 1)
        self.assertEqual((issuance.status, issuance.tx_hash), (IssuanceStatus.COMPLETED, "0xmint"))
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, issuance))

    def test_retry_on_an_unconfirmed_recorded_mint_waits_on_it_instead_of_sending(self):
        request = self._approved(issuance_request(self.token, amount=10))
        request.mark_failed("rpc down")
        issuance = self._recorded_issuance(request)
        self._mint_contract()

        self.chain.wait_for_receipt.side_effect = RuntimeError("still pending")
        with self.assertRaisesMessage(RuntimeError, "still pending"):
            self.service.execute_request(request)
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual((request.status, issuance.status, issuance.tx_hash), ("failed", "failed", "0xold"))
        self.assertEqual(issuance.error_message, "still pending")

        self.chain.wait_for_receipt.side_effect = None
        result = self.service.execute_request(request)
        self.assertEqual(result["tx_hash"], "0xold")
        self.chain.wait_for_receipt.assert_called_with("0xold")
        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual((issuance.status, request.status), (IssuanceStatus.COMPLETED, RequestStatus.EXECUTED))
        self.assertEqual(request.executed_issuance, issuance)

    def test_state_and_readiness_guards(self):
        submitted = issuance_request(self.token)
        with self.assertRaises(InvalidTokenStateException):
            self.service.execute_request(submitted)
        submitted.refresh_from_db()
        self.assertEqual(submitted.status, RequestStatus.SUBMITTED)

        undeployed = self._approved(issuance_request(self.tenant.token))
        with self.assertRaises(InvalidTokenStateException):
            self.service.execute_request(undeployed)
        undeployed.refresh_from_db()
        self.assertEqual(undeployed.review_notes, "Execution failed: Token is not deployed on blockchain")

        no_wallet = self._approved(self.tenant.capital_increase)
        with patch("companies.models.Company.get_primary_wallet", return_value=None):
            with patch.object(ShareTokenService, "increase_authorized_shares", side_effect=RuntimeError("revert")):
                with self.assertRaisesMessage(RuntimeError, "revert"):
                    self.service.execute_request(no_wallet)
        no_wallet.refresh_from_db()
        self.assertEqual((no_wallet.status, no_wallet.review_notes), (RequestStatus.FAILED, "Execution failed: revert"))
        self.assertFalse(ShareIssuance.objects.exists())


class ExecutingIssuanceSweepTest(TestCase):
    """check_executing_issuance_requests: a worker killed after the mint was sent, before the completion writes."""

    def setUp(self):
        self.chain = patch(CHAIN_CLIENT).start().return_value
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token

    def _stuck(self, tx_hash="0xmint", minutes=11):
        request = issuance_request(self.token, amount=10)
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(
            status=RequestStatus.EXECUTING, updated_at=timezone.now() - timedelta(minutes=minutes)
        )
        issuance = ShareIssuance.objects.create(
            token=self.token,
            recipient_address=RECIPIENT,
            amount="10",
            status=IssuanceStatus.PROCESSING,
            tx_hash=tx_hash,
            idempotency_key=ShareTokenService.issuance_key(request),
        )
        request.refresh_from_db()
        return request, issuance

    def test_a_mined_mint_completes_the_request_without_sending(self):
        request, issuance = self._stuck()
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}

        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 1})

        self.chain.get_transaction_receipt.assert_called_once_with("0xmint")
        self.chain.send_transaction.assert_not_called()
        self.chain.wait_for_receipt.assert_not_called()
        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, issuance))
        self.assertEqual((issuance.status, issuance.block_number), (IssuanceStatus.COMPLETED, 9))
        self.assertEqual(ShareIssuance.objects.completed_supply(self.token), 10)
        self.assertEqual(check_executing_issuance_requests(), {"checked": 0, "resolved": 0})

    def test_a_reverted_mint_fails_the_request_so_a_retry_mints_afresh(self):
        request, issuance = self._stuck()
        self.chain.get_transaction_receipt.return_value = {"status": 0, **RECEIPT}

        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 1})

        request.refresh_from_db()
        issuance.refresh_from_db()
        self.assertEqual(
            (request.status, request.review_notes), ("failed", "Execution failed: Transaction reverted: 0xmint")
        )
        self.assertTrue(request.can_be_executed)
        self.assertEqual((issuance.status, issuance.tx_hash), (IssuanceStatus.FAILED, None))
        self.assertIsNone(request.executed_issuance)

    def _stuck_increase(self, tx_hash="0xset", minutes=11):
        request = self.tenant.capital_increase
        CapitalIncreaseRequest.objects.filter(pk=request.pk).update(
            status=RequestStatus.EXECUTING, updated_at=timezone.now() - timedelta(minutes=minutes)
        )
        record = None
        if tx_hash:
            record = BlockchainTransaction.objects.create(
                tx_type=TransactionType.OTHER,
                status=TransactionStatus.SUBMITTED,
                tx_hash=tx_hash,
                from_address=SIGNER,
                to_address=self.token.contract_address,
                function_name="setAuthorizedShares",
                related_model="tokens.CapitalIncreaseRequest",
                related_uuid=request.uuid,
            )
        request.refresh_from_db()
        return request, record

    def test_a_mined_set_authorized_completes_the_increase_and_writes_the_cap_without_sending(self):
        request, record = self._stuck_increase()
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}

        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 1})

        self.chain.get_transaction_receipt.assert_called_once_with("0xset")
        self.chain.send_transaction.assert_not_called()
        request.refresh_from_db()
        record.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((request.status, request.executed_issuance), (RequestStatus.EXECUTED, None))
        self.assertEqual((record.status, record.block_number), (TransactionStatus.CONFIRMED, 9))
        self.assertEqual(self.token.total_supply, "1100")
        self.assertEqual(check_executing_issuance_requests(), {"checked": 0, "resolved": 0})

    def test_a_reverted_set_authorized_fails_the_increase_so_a_retry_sends_afresh(self):
        request, record = self._stuck_increase()
        self.chain.get_transaction_receipt.return_value = {"status": 0, **RECEIPT}

        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 1})

        request.refresh_from_db()
        record.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(
            (request.status, request.review_notes), ("failed", "Execution failed: Transaction reverted: 0xset")
        )
        self.assertTrue(request.can_be_executed)
        self.assertEqual(record.status, TransactionStatus.REVERTED)
        self.assertEqual(self.token.total_supply, "1000")

    def test_an_increase_another_worker_completed_meanwhile_is_left_alone(self):
        """The sweep read EXECUTING, the executor finished before the lock: no second cap write, no confirm."""
        request, record = self._stuck_increase()
        self.chain.get_transaction_receipt.return_value = {"status": 1, **RECEIPT}
        CapitalIncreaseRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTED)
        ShareToken.objects.filter(pk=self.token.pk).update(total_supply="1500")

        service = ShareTokenService()
        with self.assertLogs("tokens.services.share_token_service", "INFO") as logs:
            self.assertIsNone(service.resolve_executing_capital_increase(request))

        self.assertIn("completed by another worker", logs.output[-1])
        record.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual((record.status, self.token.total_supply), (TransactionStatus.SUBMITTED, "1500"))
        self.chain.send_transaction.assert_not_called()

    def test_an_increase_with_nothing_recorded_is_only_logged(self):
        request, _ = self._stuck_increase(tx_hash=None)
        with self.assertLogs("tokens.services.share_token_service", "WARNING") as logs:
            self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 0})
        self.assertIn("no setAuthorizedShares recorded", logs.output[0])
        self.chain.get_transaction_receipt.assert_not_called()
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTING)

    def test_pending_fresh_hashless_and_unreadable_rows_are_left_executing(self):
        self.chain.get_transaction_receipt.return_value = None
        pending, _ = self._stuck()
        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 0})

        fresh, _ = self._stuck(minutes=1)
        self.assertEqual(check_executing_issuance_requests(), {"checked": 1, "resolved": 0})

        hashless, _ = self._stuck(tx_hash=None)
        with self.assertLogs("tokens.services.share_token_service", "WARNING") as logs:
            self.assertEqual(check_executing_issuance_requests(), {"checked": 2, "resolved": 0})
        self.assertIn("no mint recorded", logs.output[0])

        self.chain.get_transaction_receipt.side_effect = ConnectionError("rpc down")
        self.assertEqual(check_executing_issuance_requests(), {"checked": 2, "resolved": 0})
        self.chain.send_transaction.assert_not_called()
        for request in (pending, fresh, hashless):
            request.refresh_from_db()
            self.assertEqual(request.status, RequestStatus.EXECUTING)


class ExecuteReviewRequestTaskTest(TestCase):
    def setUp(self):
        patcher = patch(CHAIN_CLIENT)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tenant = make_tenant("owner")

    def test_missing_request_answers_without_raising(self):
        result = execute_review_request_task(model_label="tokens.CapitalIncreaseRequest", request_uuid=str(uuid4()))
        self.assertEqual(result, {"success": False, "error": "Request not found"})

    def test_state_guard_answers_with_the_reason(self):
        self.tenant.capital_increase.submit(self.tenant.user)
        result = execute_review_request_task(
            model_label="tokens.CapitalIncreaseRequest", request_uuid=str(self.tenant.capital_increase.uuid)
        )
        self.assertEqual(result, {"success": False, "error": "Cannot execute request with status 'Submitted'"})

    def test_executes_the_model_named_by_the_label_with_the_executing_user(self):
        request = issuance_request(self.tenant.deployed_token, submitted_at=timezone.now())
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        with patch.object(ShareTokenService, "execute_request", return_value={"tx_hash": "0x1"}) as execute:
            result = execute_review_request_task(
                model_label="tokens.ShareIssuanceRequest",
                request_uuid=str(request.uuid),
                executed_by=self.tenant.user.pk,
            )

        self.assertEqual(result, {"success": True, "tx_hash": "0x1"})
        self.assertEqual(execute.call_args.args[0], request)
        self.assertIsInstance(execute.call_args.args[0], ShareIssuanceRequest)
        self.assertEqual(execute.call_args.kwargs, {"executed_by": self.tenant.user})
        self.assertEqual(CapitalIncreaseRequest.objects.count(), 1)

    def test_refusal_answers_with_the_reason_and_does_not_retry(self):
        request = issuance_request(self.tenant.deployed_token, submitted_at=timezone.now())
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        with patch.object(ShareTokenService, "execute_request", side_effect=IssuanceRefusedException(NOT_WHITELISTED)):
            result = execute_review_request_task(
                model_label="tokens.ShareIssuanceRequest", request_uuid=str(request.uuid)
            )
        self.assertEqual(result, {"success": False, "error": NOT_WHITELISTED})

    def test_malformed_recipient_answers_with_the_reason_and_does_not_retry(self):
        request = issuance_request(self.tenant.deployed_token, submitted_at=timezone.now())
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        with patch(CHAIN_CLIENT) as client:
            client.return_value.is_valid_address.return_value = False
            result = execute_review_request_task(
                model_label="tokens.ShareIssuanceRequest", request_uuid=str(request.uuid)
            )
        self.assertEqual(result, {"success": False, "error": str(InvalidRecipientAddressException().detail)})
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.APPROVED)
