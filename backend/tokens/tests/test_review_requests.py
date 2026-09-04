"""The shared review workflow: model transitions, dilution, the status data migration, execute_request and its task."""

import importlib
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.test import TestCase
from django.utils import timezone
from web3 import Web3

from shared.tests.tenants import make_tenant
from tokens.exceptions import CompanyNotReadyException, InvalidTokenStateException
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
)
from tokens.serializers import CapitalIncreaseDetailSerializer
from tokens.services import ShareTokenService
from tokens.tasks import execute_review_request_task

RECIPIENT = "0x" + "a" * 40
CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"


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


class ExecuteRequestServiceTest(TestCase):
    def setUp(self):
        patcher = patch(CHAIN_CLIENT)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tenant = make_tenant("owner")
        self.token = self.tenant.deployed_token
        self.service = ShareTokenService()

    def _approved(self, request):
        type(request).objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        request.refresh_from_db()
        return request

    def test_capital_increase_mints_to_the_company_wallet_and_bumps_supply(self):
        request = self._approved(self.tenant.capital_increase)
        chain_result = {
            "set_authorized_tx_hash": "0xset",
            "mint_tx_hash": "0xmint",
            "new_authorized_total": 1100,
            "block_number": 5,
            "gas_used": 21000,
        }
        with patch.object(ShareTokenService, "increase_authorized_shares", return_value=chain_result) as increase:
            result = self.service.execute_request(request)

        self.assertEqual(result, chain_result)
        increase.assert_called_once_with(self.token.contract_address, 100, self.tenant.wallet.address)
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        self.assertEqual(self.token.total_supply, "1100")
        issuance = request.executed_issuance
        self.assertEqual(issuance.status, IssuanceStatus.COMPLETED)
        self.assertEqual((issuance.tx_hash, issuance.block_number, issuance.amount), ("0xmint", 5, "100"))
        self.assertEqual(issuance.recipient_address, Web3.to_checksum_address(self.tenant.wallet.address))
        self.assertEqual(issuance.recipient_name, f"{self.tenant.company.name} Primary Wallet")
        self.assertEqual(issuance.reason, "Capital increase: Growth")
        self.assertEqual(issuance.capitalincreaserequest, request)

    def test_issuance_request_mints_to_its_recipient(self):
        request = self._approved(issuance_request(self.token, amount=10))
        chain_result = {"tx_hash": "0xmint", "block_number": 7, "gas_used": 21000}
        with patch.object(ShareTokenService, "_mint_to", return_value=chain_result) as mint:
            self.assertEqual(self.service.execute_request(request), chain_result)

        mint.assert_called_once_with(self.token.contract_address, RECIPIENT, 10)
        request.refresh_from_db()
        self.token.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.EXECUTED)
        self.assertEqual(self.token.total_supply, "1010")
        issuance = request.executed_issuance
        self.assertEqual(issuance.recipient_address, Web3.to_checksum_address(RECIPIENT))
        self.assertEqual(
            (issuance.recipient_name, issuance.issuance_type, issuance.amount), ("Alice", "additional", "10")
        )
        self.assertEqual(issuance.reason, "Issuance request: Bonus")
        self.assertEqual(issuance.shareissuancerequest, request)

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
        self.assertIsNone(request.executed_issuance)

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
            with self.assertRaises(CompanyNotReadyException):
                self.service.execute_request(no_wallet)
        no_wallet.refresh_from_db()
        self.assertEqual(no_wallet.status, RequestStatus.FAILED)
        self.assertFalse(ShareIssuance.objects.exists())


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

    def test_executes_the_model_named_by_the_label(self):
        request = issuance_request(self.tenant.deployed_token, submitted_at=timezone.now())
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.APPROVED)
        with patch.object(ShareTokenService, "execute_request", return_value={"tx_hash": "0x1"}) as execute:
            result = execute_review_request_task(
                model_label="tokens.ShareIssuanceRequest", request_uuid=str(request.uuid)
            )

        self.assertEqual(result, {"success": True, "tx_hash": "0x1"})
        self.assertEqual(execute.call_args.args[0], request)
        self.assertIsInstance(execute.call_args.args[0], ShareIssuanceRequest)
        self.assertEqual(CapitalIncreaseRequest.objects.count(), 1)
