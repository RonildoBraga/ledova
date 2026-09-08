from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus, CompanyType
from shared.tests.tenants import make_tenant
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


class ShareTokenDecimalsCannotBePersistedTest(TestCase):

    def setUp(self):
        self.token = make_tenant("whole-shares").token

    def test_database_updates_cannot_make_a_share_fractional(self):
        for decimals in (1, 6, 18):
            with self.subTest(decimals=decimals):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    ShareToken.objects.filter(pk=self.token.pk).update(decimals=decimals)
                self.token.refresh_from_db()
                self.assertEqual(self.token.decimals, 0)

    def test_model_validation_refuses_nonzero_decimals_before_saving(self):
        self.token.decimals = 1

        with self.assertRaises(ValidationError) as caught:
            self.token.full_clean()

        self.assertIn("decimals", caught.exception.message_dict)

    def test_zero_remains_valid_and_persistable(self):
        self.token.full_clean()
        ShareToken.objects.filter(pk=self.token.pk).update(decimals=0)
        self.token.refresh_from_db()

        self.assertEqual(self.token.decimals, 0)
