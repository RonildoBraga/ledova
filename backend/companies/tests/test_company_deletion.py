from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from web3 import Web3

from companies.models import Company, CompanyStatus
from offerings.models import Offering, OfferingExemption, Subscription
from tokens.models import (
    CapitalIncreaseRequest,
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
    ShareToken,
    ShareTokenStatus,
)
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()

HOLDER = Web3.to_checksum_address("0x" + "b7" * 20)
CONTRACT = Web3.to_checksum_address("0x" + "c7" * 20)


class CompanyDeletionTest(APITestCase):

    def setUp(self):
        self.owner = User.objects.create_user(email="issuer@deletion.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Undeletable Pty Ltd", acn="444444444", status=CompanyStatus.ACTIVE
        )
        self.token = ShareToken.objects.create(
            company=self.company,
            name="Undeletable ordinary shares",
            symbol="UND",
            total_supply="10000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=CONTRACT,
        )
        self.issuance = ShareIssuance.objects.create(
            token=self.token,
            recipient_address=HOLDER,
            amount="100",
            status=IssuanceStatus.COMPLETED,
            completed_at=timezone.now(),
        )
        self.issuance_request = ShareIssuanceRequest.objects.create(
            token=self.token,
            recipient_address=HOLDER,
            amount=100,
            reason="Allotment",
            status=RequestStatus.EXECUTED,
            executed_issuance=self.issuance,
        )
        self.capital_increase = CapitalIncreaseRequest.objects.create(
            token=self.token,
            additional_shares=100,
            new_authorized_total=10100,
            purpose="Growth",
            board_resolution_reference="BOARD-1",
        )
        self.offering = Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("2.50"),
            minimum_shares=1,
            target_shares=10,
            cap_shares=1000,
            opens_at=timezone.now() - timedelta(days=1),
        )
        investor = User.objects.create_user(email="investor@deletion.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=investor, full_name="Ivy Investor")
        self.account = UserAccount.objects.create(account_number="DEL-1")
        self.account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(user_account=self.account, address=HOLDER, chain="base")
        self.subscription = Subscription.objects.create(
            offering=self.offering,
            user_account=self.account,
            wallet=self.wallet,
            quantity=100,
            price_per_share=Decimal("2.50"),
            amount_due=Decimal("250.00"),
            issuance_request=self.issuance_request,
        )
        self.client.force_authenticate(self.owner)

    def _delete(self, company):
        return self.client.delete(f"/api/v1/companies/{company.uuid}/")

    def _register_rows_survive(self):
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
        self.assertTrue(ShareToken.objects.filter(pk=self.token.pk).exists())
        self.assertTrue(ShareIssuance.objects.filter(pk=self.issuance.pk).exists())
        self.assertTrue(ShareIssuanceRequest.objects.filter(pk=self.issuance_request.pk).exists())
        self.assertTrue(CapitalIncreaseRequest.objects.filter(pk=self.capital_increase.pk).exists())
        self.assertTrue(Offering.objects.filter(pk=self.offering.pk).exists())
        self.assertTrue(Subscription.objects.filter(pk=self.subscription.pk).exists())

    def test_deleting_a_company_that_holds_a_register_is_refused_and_every_row_survives(self):
        response = self._delete(self.company)

        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("register of members", response.json()["detail"])
        self.assertIn("Delist", response.json()["detail"])
        self._register_rows_survive()

    def test_the_refusal_names_how_many_share_classes_hold_the_company_open(self):
        ShareToken.objects.create(
            company=self.company,
            name="Second class",
            symbol="UND2",
            total_supply="1000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=Web3.to_checksum_address("0x" + "d7" * 20),
        )

        response = self._delete(self.company)

        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(response.json()["detail"].startswith("2 deployed share class(es)"))

    def test_an_undeployed_share_class_still_refuses_the_delete_at_the_database(self):
        company = Company.objects.create(owner=self.owner, name="Draft Pty Ltd", acn="555555555")
        draft = ShareToken.objects.create(company=company, name="Draft shares", symbol="DRF", total_supply="100")

        response = self._delete(company)

        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(ShareToken.objects.filter(pk=draft.pk).exists())
        self.assertTrue(Company.objects.filter(pk=company.pk).exists())

    def test_a_company_with_no_share_classes_is_still_deletable(self):
        company = Company.objects.create(owner=self.owner, name="Empty Pty Ltd", acn="666666666")

        response = self._delete(company)

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Company.objects.filter(pk=company.pk).exists())

    @patch("companies.services.company.send_push_notification")
    def test_delisting_is_the_escape_hatch_the_refusal_points_at(self, _notify):
        operator = User.objects.create_user(email="operator@deletion.test", password="pw-12345678", is_staff=True)
        self.client.force_authenticate(operator)

        response = self.client.post(
            f"/api/v1/companies/{self.company.uuid}/status/", {"status": CompanyStatus.DELISTED, "reason": "Wound up"}
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.company.refresh_from_db()
        self.assertEqual(self.company.status, CompanyStatus.DELISTED)
        self._register_rows_survive()


class DeployedShareClassDeletionTest(APITestCase):

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@shareclass.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Chain Bypass Pty Ltd", acn="555555555", status=CompanyStatus.ACTIVE
        )
        self.deployed = ShareToken.objects.create(
            company=self.company,
            name="Deployed ordinary shares",
            symbol="DEP",
            total_supply="10000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address=Web3.to_checksum_address("0x" + "d7" * 20),
        )
        self.client.force_authenticate(self.owner)

    def test_the_owner_cannot_delete_a_deployed_share_class_that_has_no_issuances_yet(self):
        response = self.client.delete(f"/api/v1/tokens/{self.deployed.uuid}/")

        self.assertEqual(response.status_code, 409)
        self.assertIn("DEP", response.json()["detail"])
        self.assertTrue(ShareToken.objects.filter(pk=self.deployed.pk).exists())

    def test_deleting_the_share_class_first_does_not_open_a_path_to_deleting_the_company(self):
        token_response = self.client.delete(f"/api/v1/tokens/{self.deployed.uuid}/")
        company_response = self.client.delete(f"/api/v1/companies/{self.company.uuid}/")

        self.assertEqual(token_response.status_code, 409)
        self.assertEqual(company_response.status_code, 409)
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())
        self.assertTrue(ShareToken.objects.filter(pk=self.deployed.pk).exists())

    def test_an_undeployed_share_class_is_still_deletable(self):
        draft = ShareToken.objects.create(company=self.company, name="Draft shares", symbol="DRF", total_supply="100")

        response = self.client.delete(f"/api/v1/tokens/{draft.uuid}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ShareToken.objects.filter(pk=draft.pk).exists())
