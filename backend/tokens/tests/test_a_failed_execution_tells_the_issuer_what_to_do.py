from unittest.mock import PropertyMock, patch

from django.contrib import admin
from django.test import TestCase
from requests.exceptions import ConnectionError as RequestsConnectionError
from web3 import Web3

from blockchain.models import BlockchainTransaction
from shared.tests.tenants import make_tenant
from tokens.admin.capital_increase import CapitalIncreaseAdmin
from tokens.admin.share_issuance_request import ShareIssuanceRequestAdmin
from tokens.exceptions import TokenDeploymentFailedException
from tokens.models import (
    CapitalIncreaseRequest,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
)
from tokens.serializers import CapitalIncreaseDetailSerializer
from tokens.serializers.share_issuance_request import ShareIssuanceRequestSerializer
from tokens.services import ShareTokenService
from tokens.services.share_token_service import (
    CAPITAL_INCREASE_EXECUTION_FAILED,
    ISSUANCE_EXECUTION_FAILED,
)
from tokens.tests.test_review_requests import (
    CHAIN_CLIENT,
    SIGNER,
    SUPPLY,
    WHITELISTED,
    issuance_request,
)

KEY = "pR3t3nd1ngT0B3aReAlK3y"
RPC_URL = f"https://base-sepolia.g.alchemy.com/v2/{KEY}"
PROVIDER_TEXT = f"Max retries exceeded with url: {RPC_URL}"
SIGNER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


class WhatTheIssuerReadsAfterAFailedExecutionTest(TestCase):

    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
        self.chain = chain
        chain.is_valid_address.return_value = True
        chain.to_checksum_address.side_effect = Web3.to_checksum_address
        chain.get_address_from_private_key.return_value = SIGNER
        chain.load_contract.return_value.functions.paused.return_value.call.return_value = False
        patch(WHITELISTED, return_value=True).start()
        patch(SUPPLY, return_value=(1000, 0)).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("failednote")
        self.token = self.tenant.deployed_token
        self.service = ShareTokenService()

    def _approved(self, request):
        request.status = RequestStatus.APPROVED
        request.reviewed_by = self.tenant.user
        request.save(update_fields=["status", "reviewed_by", "updated_at"])
        return request

    def a_failed_issuance(self):
        request = self._approved(issuance_request(self.token))
        with patch.object(ShareTokenService, "_mint_to", side_effect=RequestsConnectionError(PROVIDER_TEXT)):
            with self.assertRaises(RequestsConnectionError):
                self.service.execute_request(request)
        request.refresh_from_db()
        return request

    def a_failed_capital_increase(self):
        request = self._approved(self.tenant.capital_increase)
        with patch("tokens.services.share_token_service.primary_wallet_for", return_value=None):
            with patch.object(
                ShareTokenService, "increase_authorized_shares", side_effect=RequestsConnectionError(PROVIDER_TEXT)
            ):
                with self.assertRaises(RequestsConnectionError):
                    self.service.execute_request(request)
        request.refresh_from_db()
        return request

    def test_the_node_key_never_reaches_the_issuer_through_an_issuance_request(self):
        request = self.a_failed_issuance()

        served = str(ShareIssuanceRequestSerializer(request).data)

        self.assertNotIn(KEY, served)
        self.assertNotIn("alchemy.com", served)
        self.assertIn(ISSUANCE_EXECUTION_FAILED, served)

    def test_the_node_key_never_reaches_the_issuer_through_a_capital_increase(self):
        request = self.a_failed_capital_increase()

        served = str(CapitalIncreaseDetailSerializer(request).data)

        self.assertNotIn(KEY, served)
        self.assertNotIn("alchemy.com", served)
        self.assertIn(CAPITAL_INCREASE_EXECUTION_FAILED, served)

    def test_the_note_requires_an_operator_to_check_the_chain_before_retrying(self):
        request = self.a_failed_issuance()

        self.assertIn("could not be confirmed", request.execution_notes)
        self.assertIn("An operator must check", request.execution_notes)
        self.assertIn("on-chain state before deciding whether to retry", request.execution_notes)
        self.assertEqual(request.review_notes, "")
        self.assertTrue(request.can_be_executed)

    def test_the_operator_keeps_the_diagnostic_the_issuer_does_not_get(self):
        self.a_failed_issuance()

        issuance = ShareIssuance.objects.get(token=self.token)

        self.assertIn(KEY, issuance.error_message)

    def a_capital_increase_that_reached_the_node(self):
        request = self._approved(self.tenant.capital_increase)
        self.chain.send_transaction.side_effect = RequestsConnectionError(PROVIDER_TEXT)
        with patch.object(ShareTokenService, "signer_key", new_callable=PropertyMock, return_value=SIGNER_KEY):
            with patch("tokens.services.share_token_service.primary_wallet_for", return_value=None):
                with self.assertRaises(TokenDeploymentFailedException):
                    self.service.execute_request(request)
        request.refresh_from_db()
        return request

    def test_the_operator_keeps_the_capital_increase_diagnostic_the_issuer_does_not_get(self):
        request = self.a_capital_increase_that_reached_the_node()

        recorded = BlockchainTransaction.objects.get(
            related_model=CapitalIncreaseRequest._meta.label, related_uuid=request.uuid
        )

        self.assertIn(KEY, recorded.error_message)
        self.assertNotIn(KEY, str(CapitalIncreaseDetailSerializer(request).data))

    def test_the_admin_puts_that_diagnostic_in_front_of_the_operator(self):
        request = self.a_capital_increase_that_reached_the_node()
        shown = CapitalIncreaseAdmin(CapitalIncreaseRequest, admin.site).last_execution_error(request)

        self.assertIn(KEY, shown)

    def test_a_request_that_never_failed_shows_no_error_row(self):
        request = self._approved(self.tenant.capital_increase)

        shown = CapitalIncreaseAdmin(CapitalIncreaseRequest, admin.site).last_execution_error(request)

        self.assertEqual(shown, "-")

    def issuance_admin(self):
        return ShareIssuanceRequestAdmin(ShareIssuanceRequest, admin.site)

    def test_the_admin_puts_the_issuance_diagnostic_in_front_of_the_operator_too(self):
        request = self.a_failed_issuance()

        shown = self.issuance_admin().last_execution_error(request)

        self.assertIn(KEY, shown)

    def test_an_issuance_request_that_never_failed_shows_no_error_row(self):
        request = self._approved(issuance_request(self.token))

        shown = self.issuance_admin().last_execution_error(request)

        self.assertEqual(shown, "-")

    def test_the_issuance_request_carries_no_blockchain_transaction_of_its_own(self):
        request = self.a_failed_issuance()

        self.assertFalse(
            BlockchainTransaction.objects.filter(
                related_model=ShareIssuanceRequest._meta.label, related_uuid=request.uuid
            ).exists()
        )

    def test_one_capital_increase_failure_is_logged_once(self):
        with self.assertLogs("tokens.services.share_token_service", level="ERROR") as logged:
            self.a_failed_capital_increase()

        about_this_failure = [line for line in logged.output if "Capital increase" in line]
        self.assertEqual(len(about_this_failure), 1, about_this_failure)

    def test_a_capital_increase_says_the_cap_rather_than_the_shares(self):
        request = self.a_failed_capital_increase()

        self.assertIn("capital increase could not be confirmed", request.execution_notes)
        self.assertEqual(request.review_notes, "")
        self.assertEqual(CapitalIncreaseRequest.objects.get(pk=request.pk).status, RequestStatus.FAILED)

    def test_internal_and_legacy_review_notes_remain_available_only_to_the_operator(self):
        for request, serializer in (
            (self._approved(issuance_request(self.token)), ShareIssuanceRequestSerializer),
            (self._approved(self.tenant.capital_increase), CapitalIncreaseDetailSerializer),
        ):
            with self.subTest(request=type(request).__name__):
                for note in (f"Reviewer diagnostic: {PROVIDER_TEXT}", f"Execution failed: {PROVIDER_TEXT}"):
                    request.review_notes = note
                    request.save(update_fields=["review_notes"])

                    served = serializer(request).data

                    self.assertNotIn("review_notes", served)
                    self.assertNotIn(KEY, str(served))
                    request.refresh_from_db()
                    self.assertEqual(request.review_notes, note)
