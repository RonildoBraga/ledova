from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase
from web3 import Web3

from companies.models import Company
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareToken,
    ShareTokenStatus,
)

User = get_user_model()


class CompanyStatsTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="stats-owner@example.test", password="pw-12345678")
        self.company = Company.objects.create(owner=self.owner, name="Stats Pty Ltd", acn="444555666")
        self.deployed = ShareToken.objects.create(
            company=self.company,
            name="Deployed shares",
            symbol="DEP",
            total_supply="1000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + "c" * 40,
        )
        self.draft = ShareToken.objects.create(
            company=self.company, name="Draft shares", symbol="DRF", total_supply="1"
        )

    def _issuance(self, token, recipient, status=IssuanceStatus.COMPLETED):
        return ShareIssuance.objects.create(token=token, recipient_address=recipient, amount="10", status=status)

    def _a_second_class(self, number):
        return ShareToken.objects.create(
            company=self.company,
            name=f"Class {number} shares",
            symbol=f"IN{number}",
            total_supply="1000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=f"0x{number + 1:040x}",
        )

    def _capital_increase(self, status, token=None):
        return CapitalIncreaseRequest.objects.create(
            token=token or self.deployed,
            additional_shares=100,
            new_authorized_total=1100,
            purpose="Growth",
            board_resolution_reference=f"BOARD-{status}",
            status=status,
        )

    def test_stats_keys_and_counts_read_by_the_clients(self):
        holder_a, holder_b = "0x" + "1" * 40, "0x" + "2" * 40
        self._issuance(self.deployed, holder_a)
        self._issuance(self.deployed, holder_a)
        self._issuance(self.deployed, holder_b)
        self._issuance(self.deployed, "0x" + "3" * 40, status=IssuanceStatus.PENDING)
        self._issuance(self.draft, "0x" + "4" * 40)
        in_flight = (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW, RequestStatus.APPROVED)
        for index, status in enumerate(in_flight):
            self._capital_increase(status, token=self._a_second_class(index))
        for status in set(RequestStatus) - set(in_flight):
            self._capital_increase(status)
        self.client.force_authenticate(self.owner)

        response = self.client.get(f"/api/v1/companies/{self.company.uuid}/stats/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"totalTokens": 4, "totalShareholders": 2, "pendingActions": 3, "pendingCapitalIncreases": 3},
        )

    def test_the_shareholder_count_never_reads_the_chain_and_costs_the_same_at_any_size(self):
        self.client.force_authenticate(self.owner)
        url = f"/api/v1/companies/{self.company.uuid}/stats/"

        def allot(start, stop):
            for index in range(start, stop):
                self._issuance(self.deployed, Web3.to_checksum_address(f"0x{index + 1:040x}"))

        with patch("tokens.services.share_token_service.ShareTokenService.get_token_balance") as balance:
            allot(0, 2)
            with CaptureQueriesContext(connection) as few:
                self.client.get(url)
            allot(2, 200)
            with CaptureQueriesContext(connection) as many:
                response = self.client.get(url)

        self.assertEqual(response.json()["totalShareholders"], 200)
        self.assertEqual(len(many), len(few))
        balance.assert_not_called()
