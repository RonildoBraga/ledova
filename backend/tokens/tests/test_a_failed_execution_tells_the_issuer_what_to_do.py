from unittest.mock import patch

from django.test import TestCase
from requests.exceptions import ConnectionError as RequestsConnectionError
from web3 import Web3

from shared.tests.tenants import make_tenant
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareIssuance
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


class WhatTheIssuerReadsAfterAFailedExecutionTest(TestCase):

    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
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

    def test_the_note_says_what_a_retry_does_rather_than_only_that_it_failed(self):
        request = self.a_failed_issuance()

        self.assertIn("did not complete", request.review_notes)
        self.assertIn("cannot be issued twice", request.review_notes)
        self.assertIn("execute it again", request.review_notes)
        self.assertTrue(request.can_be_executed)

    def test_the_operator_keeps_the_diagnostic_the_issuer_does_not_get(self):
        self.a_failed_issuance()

        issuance = ShareIssuance.objects.get(token=self.token)

        self.assertIn(KEY, issuance.error_message)

    def test_a_capital_increase_says_the_cap_rather_than_the_shares(self):
        request = self.a_failed_capital_increase()

        self.assertIn("cannot be raised twice", request.review_notes)
        self.assertNotIn("issued twice", request.review_notes)
        self.assertEqual(CapitalIncreaseRequest.objects.get(pk=request.pk).status, RequestStatus.FAILED)
