from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetChainDeployment
from companies.models import Company, CompanyStatus
from offerings.exceptions import (
    InvalidOfferingTransitionException,
    OfferingRefusedException,
)
from offerings.models import Offering, OfferingExemption, OfferingStatus
from offerings.services.offering import (
    ALREADY_LIVE,
    CAP_ABOVE_HEADROOM,
    COMPANY_NOT_ACTIVE,
    MAXIMUM_ABOVE_CAP,
    MINIMUM_BELOW_THRESHOLD,
    NO_PAYMENT_RAIL,
    TOKEN_NOT_DEPLOYED,
    submit_offering,
)
from operators.exceptions import SettlementAssetNotDeployedException
from operators.models import Operator
from operators.settlement import NOT_DEPLOYED
from shared.tests.tenants import make_tenant
from tokens.models import ShareIssuance
from tokens.models.choices import IssuanceStatus


class SubmitOfferingTest(TestCase):
    def setUp(self):
        self.push = patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.tenant.company.refresh_from_db()
        self.token = self.tenant.deployed_token
        self.offering = self.tenant.offering
        self.offering.refresh_from_db()

    def _refusal(self, offering=None):
        with self.assertRaises(OfferingRefusedException) as raised:
            submit_offering(offering or self.offering, submitted_by=self.tenant.user)
        return str(raised.exception.detail)

    def test_a_clean_offering_submits_and_notifies_the_owner(self):
        submit_offering(self.offering, submitted_by=self.tenant.user)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)
        self.assertEqual(self.offering.submitted_by, self.tenant.user)
        self.assertEqual(self.push.defer.call_args.kwargs["title"], "Offering submitted")

    def test_an_undeployed_share_class_is_refused(self):
        self.offering.token = self.tenant.token
        self.offering.save(update_fields=["token"])
        self.assertEqual(self._refusal(), TOKEN_NOT_DEPLOYED.format(symbol=self.tenant.token.symbol))

    def test_a_company_that_cannot_issue_is_refused(self):
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.SUSPENDED)
        self.assertEqual(
            self._refusal(),
            COMPANY_NOT_ACTIVE.format(name=self.tenant.company.name, status="suspended"),
        )

    def test_a_cap_beyond_the_unissued_headroom_names_the_capital_increase(self):
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address="0x" + "1" * 40,
            amount="950",
            status=IssuanceStatus.COMPLETED,
        )

        message = self._refusal()
        self.assertEqual(
            message,
            CAP_ABOVE_HEADROOM.format(
                cap=100, symbol=self.token.symbol, authorized=1000, issued=950, reserved=0, headroom=50
            ),
        )
        self.assertIn("CapitalIncreaseRequest", message)

    def test_a_second_offering_is_refused_by_name_while_one_is_live(self):
        opens_at = timezone.now() + timedelta(days=1)
        Offering.objects.filter(pk=self.offering.pk).update(status=OfferingStatus.APPROVED, opens_at=opens_at)
        second = Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("1.00"),
            minimum_shares=1,
            target_shares=10,
            cap_shares=20,
            opens_at=timezone.now() + timedelta(days=2),
        )
        self.assertEqual(
            self._refusal(second),
            ALREADY_LIVE.format(symbol=self.token.symbol, status="approved", opens=opens_at.date().isoformat()),
        )
        second.refresh_from_db()
        self.assertEqual(second.status, OfferingStatus.DRAFT)

    def test_a_second_offering_is_allowed_once_the_first_is_closed(self):
        Offering.objects.filter(pk=self.offering.pk).update(status=OfferingStatus.CLOSED)
        second = Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("1.00"),
            minimum_shares=1,
            target_shares=10,
            cap_shares=20,
            opens_at=timezone.now() + timedelta(days=2),
        )
        submit_offering(second, submitted_by=self.tenant.user)
        second.refresh_from_db()
        self.assertEqual(second.status, OfferingStatus.SUBMITTED)

    def test_a_cap_exactly_at_the_headroom_is_accepted(self):
        ShareIssuance.objects.create(
            token=self.token,
            recipient_address="0x" + "1" * 40,
            amount="900",
            status=IssuanceStatus.COMPLETED,
        )
        submit_offering(self.offering, submitted_by=self.tenant.user)
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

    def test_a_maximum_above_the_cap_is_refused(self):
        Offering.objects.filter(pk=self.offering.pk).update(maximum_shares=101)
        self.offering.refresh_from_db()
        self.assertEqual(self._refusal(), MAXIMUM_ABOVE_CAP.format(maximum=101, cap=100))

    def test_an_offering_with_no_payment_rail_is_refused(self):
        Offering.objects.filter(pk=self.offering.pk).update(accepts_bank_transfer=False)
        self.offering.refresh_from_db()
        self.assertEqual(self._refusal(), NO_PAYMENT_RAIL)

    def test_a_settlement_asset_without_a_deployment_is_refused(self):
        undeployed = Asset.objects.create(symbol="NODEP", name="No deployment", asset_type="stablecoin", decimals=6)
        self.offering.settlement_assets.add(undeployed)
        operator = Operator.get()
        with self.assertRaises(SettlementAssetNotDeployedException) as raised:
            submit_offering(self.offering, submitted_by=self.tenant.user)
        self.assertEqual(
            str(raised.exception.detail),
            NOT_DEPLOYED.format(symbol="NODEP", chain=operator.receiving_wallet_chain),
        )

    def test_a_settlement_asset_deployed_on_the_receiving_chain_is_accepted(self):
        asset = Asset.objects.create(symbol="DEPD", name="Deployed", asset_type="stablecoin", decimals=6)
        AssetChainDeployment.objects.create(
            asset=asset, chain=Operator.get().receiving_wallet_chain, contract_address="0x" + "7" * 40, decimals=6
        )
        Offering.objects.filter(pk=self.offering.pk).update(accepts_bank_transfer=False)
        self.offering.refresh_from_db()
        self.offering.settlement_assets.add(asset)
        submit_offering(self.offering, submitted_by=self.tenant.user)
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

    def test_the_minimum_amount_exemption_needs_the_full_threshold(self):
        Offering.objects.filter(pk=self.offering.pk).update(
            exemption=OfferingExemption.MINIMUM_AMOUNT, minimum_shares=10, price_per_share=Decimal("100.00")
        )
        self.offering.refresh_from_db()
        self.assertEqual(
            self._refusal(),
            MINIMUM_BELOW_THRESHOLD.format(
                threshold=Decimal("500000.00"), shares=10, price=Decimal("100.00"), amount=Decimal("1000.00")
            ),
        )

    def test_the_minimum_amount_exemption_passes_at_the_threshold(self):
        Offering.objects.filter(pk=self.offering.pk).update(
            exemption=OfferingExemption.MINIMUM_AMOUNT,
            minimum_shares=50,
            target_shares=60,
            cap_shares=70,
            price_per_share=Decimal("10000.00"),
        )
        self.offering.refresh_from_db()
        submit_offering(self.offering, submitted_by=self.tenant.user)
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

    def test_another_exemption_skips_the_arithmetic(self):
        Offering.objects.filter(pk=self.offering.pk).update(
            exemption=OfferingExemption.WHOLESALE_CLIENT, price_per_share=Decimal("0.01")
        )
        self.offering.refresh_from_db()
        submit_offering(self.offering, submitted_by=self.tenant.user)
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

    def test_a_submitted_offering_cannot_be_submitted_twice(self):
        submit_offering(self.offering, submitted_by=self.tenant.user)
        with self.assertRaises(InvalidOfferingTransitionException) as raised:
            submit_offering(self.offering, submitted_by=self.tenant.user)
        self.assertEqual(
            str(raised.exception.detail), "Cannot transition from 'Submitted for Review' to 'Submitted for Review'."
        )
