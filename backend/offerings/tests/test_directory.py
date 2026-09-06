from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APITestCase

from companies.models import Company
from offerings.models import Offering, OfferingStatus
from offerings.serializers import DIRECTORY_COMPANY_FIELDS
from shared.tests.tenants import (
    make_associated,
    make_eligible,
    make_tenant,
    open_to_investors,
)
from tokens.models import ShareIssuance
from tokens.models.choices import IssuanceStatus
from users.models import (
    InvestorClassification,
    InvestorClassificationStatus,
    UserProfile,
)

LIST = "/api/v1/directory/tokens/"


def _detail(token):
    return f"{LIST}{token.uuid}/"


class DirectoryEligibilityTest(APITestCase):
    def setUp(self):
        self.investor = make_tenant("investor")
        self.issuer = make_tenant("issuer")
        open_to_investors(self.issuer)
        self.client.force_authenticate(self.investor.user)

    def test_ineligible_caller_sees_an_empty_list(self):
        response = self.client.get(LIST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_ineligible_detail_is_byte_identical_to_a_phantom_uuid(self):
        real = self.client.get(_detail(self.issuer.deployed_token))
        phantom = self.client.get(f"{LIST}{uuid4()}/")
        self.assertEqual(real.status_code, 404)
        self.assertEqual(phantom.status_code, 404)
        self.assertEqual(real.content, phantom.content)

    def test_eligible_caller_sees_the_listed_share_class(self):
        make_eligible(self.investor)
        response = self.client.get(LIST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(self.issuer.deployed_token.uuid)])
        self.assertEqual(self.client.get(_detail(self.issuer.deployed_token)).status_code, 200)

    def test_a_company_not_open_to_investors_never_appears(self):
        make_eligible(self.investor)
        Company.objects.filter(pk=self.issuer.company.pk).update(is_open_to_investors=False)
        response = self.client.get(LIST)
        self.assertEqual(response.json()["results"], [])
        real = self.client.get(_detail(self.issuer.deployed_token))
        phantom = self.client.get(f"{LIST}{uuid4()}/")
        self.assertEqual(real.content, phantom.content)

    def test_an_undeployed_share_class_never_appears(self):
        make_eligible(self.investor)
        response = self.client.get(LIST)
        listed = {row["uuid"] for row in response.json()["results"]}
        self.assertNotIn(str(self.issuer.token.uuid), listed)


class DirectoryPayloadTest(APITestCase):
    def setUp(self):
        self.investor = make_tenant("investor")
        self.issuer = make_tenant("issuer")
        make_eligible(self.investor)
        open_to_investors(self.issuer)
        Company.objects.filter(pk=self.issuer.company.pk).update(
            trading_name="Issuer Trading", industry="Agriculture", city="Byron Bay", state="NSW"
        )
        self.client.force_authenticate(self.investor.user)

    def _row(self):
        return self.client.get(LIST).json()["results"][0]

    def test_the_company_block_carries_exactly_four_public_keys(self):
        self.assertEqual(set(self._row()["company"]), {"displayName", "industry", "city", "state"})
        self.assertEqual(DIRECTORY_COMPANY_FIELDS, ["display_name", "industry", "city", "state"])

    def test_the_company_block_leaks_no_private_field(self):
        row = self._row()
        body = self.client.get(LIST).content.decode()
        for leaked in ("acn", "abn", "owner", "apiKey", "api_key", "operatorWallet", "operator_wallet"):
            self.assertNotIn(leaked, row["company"])
        self.assertNotIn(self.issuer.company.acn, body)
        self.assertNotIn(self.issuer.company.api_key, body)

    def test_the_company_block_shows_the_trading_name(self):
        self.assertEqual(self._row()["company"]["displayName"], "Issuer Trading")

    def test_issued_shares_are_annotated_set_wise(self):
        for amount in ("40", "60"):
            ShareIssuance.objects.create(
                token=self.issuer.deployed_token,
                recipient_address="0x" + "1" * 40,
                amount=amount,
                status=IssuanceStatus.COMPLETED,
            )
        ShareIssuance.objects.create(
            token=self.issuer.deployed_token,
            recipient_address="0x" + "2" * 40,
            amount="500",
            status=IssuanceStatus.PENDING,
        )
        self.assertEqual(self._row()["issuedShares"], 100)

    def test_issued_shares_are_zero_without_any_issuance(self):
        self.assertEqual(self._row()["issuedShares"], 0)

    def _set(self, **fields):
        Offering.objects.filter(pk=self.issuer.offering.pk).update(**fields)

    def test_only_an_approved_offering_that_has_opened_is_published(self):
        self._set(opens_at=timezone.now() - timedelta(days=1))
        for status in (
            OfferingStatus.DRAFT,
            OfferingStatus.SUBMITTED,
            OfferingStatus.UNDER_REVIEW,
            OfferingStatus.REJECTED,
            OfferingStatus.WITHDRAWN,
            OfferingStatus.CLOSED,
        ):
            with self.subTest(status=status):
                self._set(status=status)
                self.assertIsNone(self._row()["openOffering"])

        self._set(status=OfferingStatus.APPROVED)
        offering = self._row()["openOffering"]
        self.assertEqual(offering["uuid"], str(self.issuer.offering.uuid))
        self.assertEqual((offering["pricePerShare"], offering["priceCurrency"]), ("2.50", "AUD"))

    def test_an_approved_offering_stays_unpublished_until_it_opens(self):
        self._set(status=OfferingStatus.APPROVED, opens_at=timezone.now() + timedelta(days=7))
        self.assertIsNone(self._row()["openOffering"])

    def test_an_approved_offering_disappears_once_it_has_closed(self):
        self._set(
            status=OfferingStatus.APPROVED,
            opens_at=timezone.now() - timedelta(days=7),
            closes_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertIsNone(self._row()["openOffering"])

    def test_the_published_offering_never_carries_a_status(self):
        self._set(status=OfferingStatus.APPROVED, opens_at=timezone.now() - timedelta(days=1))
        self.assertNotIn("status", self._row()["openOffering"])


class DirectoryAssociatedPersonTest(APITestCase):
    def setUp(self):
        self.holder = make_tenant("associate")
        self.named = make_tenant("named-issuer")
        self.stranger = make_tenant("stranger-issuer")
        open_to_investors(self.named)
        open_to_investors(self.stranger)
        self.association = make_associated(self.holder, self.named.company)
        self.client.force_authenticate(self.holder.user)

    def _listed(self):
        response = self.client.get(LIST)
        self.assertEqual(response.status_code, 200, response.content)
        return [row["uuid"] for row in response.json()["results"]]

    def _is_a_phantom(self, token):
        real = self.client.get(_detail(token))
        phantom = self.client.get(f"{LIST}{uuid4()}/")
        self.assertEqual(real.status_code, 404, real.content)
        self.assertEqual(phantom.status_code, 404, phantom.content)
        self.assertEqual(real.content, phantom.content)

    def test_the_directory_carries_the_named_issuer_and_nothing_else(self):
        self.assertEqual(self._listed(), [str(self.named.deployed_token.uuid)])

    def test_the_named_issuer_resolves_and_every_other_issuer_is_a_phantom(self):
        self.assertEqual(self.client.get(_detail(self.named.deployed_token)).status_code, 200)
        self._is_a_phantom(self.stranger.deployed_token)

    def test_the_named_issuer_becomes_a_phantom_once_it_closes_its_listing(self):
        Company.objects.filter(pk=self.named.company.pk).update(is_open_to_investors=False)
        self.assertEqual(self._listed(), [])
        self._is_a_phantom(self.named.deployed_token)

    def test_a_revoked_association_empties_the_directory_and_hides_the_named_issuer(self):
        InvestorClassification.objects.filter(pk=self.association.pk).update(
            status=InvestorClassificationStatus.REVOKED
        )
        self.assertEqual(self._listed(), [])
        self._is_a_phantom(self.named.deployed_token)

    def test_an_expired_association_empties_the_directory_and_hides_the_named_issuer(self):
        InvestorClassification.objects.filter(pk=self.association.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.assertEqual(self._listed(), [])
        self._is_a_phantom(self.named.deployed_token)

    def test_an_association_never_reaches_a_second_issuer_it_does_not_name(self):
        make_associated(self.holder, self.stranger.company)
        self.assertEqual(
            sorted(self._listed()),
            sorted([str(self.named.deployed_token.uuid), str(self.stranger.deployed_token.uuid)]),
        )

    def test_a_general_claim_beside_the_association_reaches_every_issuer(self):
        make_eligible(self.holder)
        self.assertEqual(
            sorted(self._listed()),
            sorted([str(self.named.deployed_token.uuid), str(self.stranger.deployed_token.uuid)]),
        )
        self.assertEqual(self.client.get(_detail(self.stranger.deployed_token)).status_code, 200)

    def test_an_unverified_holder_reaches_nothing_even_with_a_live_association(self):
        UserProfile.objects.filter(pk=self.holder.profile.pk).update(is_id_verified=False)
        self.assertEqual(self._listed(), [])
        self._is_a_phantom(self.named.deployed_token)

    def test_a_general_claim_alone_still_reaches_every_issuer(self):
        outsider = make_tenant("general-holder")
        make_eligible(outsider)
        self.client.force_authenticate(outsider.user)
        self.assertEqual(
            sorted(self._listed()),
            sorted([str(self.named.deployed_token.uuid), str(self.stranger.deployed_token.uuid)]),
        )

    def test_a_holder_with_neither_claim_still_reaches_nothing(self):
        nobody = make_tenant("nobody")
        self.client.force_authenticate(nobody.user)
        self.assertEqual(self._listed(), [])
        self._is_a_phantom(self.named.deployed_token)
        self._is_a_phantom(self.stranger.deployed_token)
