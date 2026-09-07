from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from tokens.models import ShareToken, ShareTokenType
from tokens.serializers.share_token import SHARES_ARE_WHOLE

User = get_user_model()

PAYLOAD = {"name": "Acme Ordinary", "symbol": "ACM", "tokenType": ShareTokenType.ORDINARY, "totalSupply": "1000"}


class AShareClassRecordsWholeUnitsTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="issuer@example.test", password="pw-12345678", is_active=True, is_email_verified=True
        )
        Company.objects.create(
            owner=self.owner,
            name="Acme Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="000000019",
            status=CompanyStatus.ACTIVE,
        )
        self.client.force_authenticate(self.owner)

    def test_a_payload_that_asks_for_fractional_shares_is_refused_and_says_why(self):
        response = self.client.post("/api/v1/tokens/", {**PAYLOAD, "decimals": 2}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["decimals"], [SHARES_ARE_WHOLE])
        self.assertFalse(ShareToken.objects.exists())

    def test_the_refusal_names_the_contract_rather_than_the_field(self):
        self.assertIn("decimals()", SHARES_ARE_WHOLE)
        self.assertIn("whole unit", SHARES_ARE_WHOLE)

    def test_a_payload_that_says_nothing_records_whole_units(self):
        response = self.client.post("/api/v1/tokens/", PAYLOAD, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ShareToken.objects.get(symbol="ACM").decimals, 0)

    def test_a_payload_that_names_zero_is_accepted_because_it_agrees_with_the_contract(self):
        response = self.client.post("/api/v1/tokens/", {**PAYLOAD, "decimals": 0}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ShareToken.objects.get(symbol="ACM").decimals, 0)
