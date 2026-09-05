from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

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

    def _capital_increase(self, status):
        return CapitalIncreaseRequest.objects.create(
            token=self.deployed,
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
        for status in RequestStatus:
            self._capital_increase(status)
        self.client.force_authenticate(self.owner)

        response = self.client.get(f"/api/v1/companies/{self.company.uuid}/stats/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"totalTokens": 1, "totalShareholders": 2, "pendingActions": 3, "pendingCapitalIncreases": 3},
        )
