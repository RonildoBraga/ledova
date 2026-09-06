from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment, AssetType
from companies.models import Company, CompanyStatus
from shared.tests.tenants import make_tenant

DETAIL_KEYS = {
    "uuid",
    "company",
    "companyUuid",
    "companyName",
    "name",
    "symbol",
    "tokenType",
    "tokenTypeDisplay",
    "status",
    "statusDisplay",
    "contractAddress",
    "chain",
    "totalSupply",
    "decimals",
    "isTransferable",
    "isDivisible",
    "deploymentTxHash",
    "deployedAt",
    "createdAt",
    "updatedAt",
}


def bridge(symbol, chain, contract_address, *, is_active=True):
    asset = Asset.objects.create(
        symbol=symbol,
        name=f"{symbol} shares",
        asset_type=AssetType.TOKENIZED_SECURITY.value,
        decimals=0,
        is_verified=True,
    )
    return AssetChainDeployment.objects.create(
        asset=asset, chain=chain, contract_address=contract_address, decimals=0, is_active=is_active
    )


class ShareTokenChainTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("chain")
        self.client.force_authenticate(self.tenant.user)
        self.token = self.tenant.deployed_token
        self.draft = self.tenant.token

    def _detail(self, token):
        response = self.client.get(f"/api/v1/tokens/{token.uuid}/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_the_chain_is_the_one_the_contract_address_is_deployed_at(self):
        bridge("CHNA", "base", self.token.contract_address)

        self.assertEqual(self._detail(self.token)["chain"], "base")

    def test_a_token_deployed_off_base_reports_its_own_chain(self):
        bridge("CHNB", "ethereum", self.token.contract_address)

        payload = self._detail(self.token)

        self.assertEqual(payload["chain"], "ethereum")
        self.assertEqual(payload["contractAddress"], self.token.contract_address)

    def test_a_deployment_of_a_different_address_is_never_borrowed(self):
        bridge("CHNC", "ethereum", "0x" + "1" * 40)

        self.assertIsNone(self._detail(self.token)["chain"])

    def test_each_token_reports_the_chain_of_its_own_address(self):
        other = self.tenant.company.tokens.create(
            name="Second class", symbol="SEC", total_supply="10", status="deployed", contract_address="0x" + "2" * 40
        )
        bridge("CHND", "base", self.token.contract_address)
        bridge("CHNE", "ethereum", other.contract_address)

        self.assertEqual(self._detail(self.token)["chain"], "base")
        self.assertEqual(self._detail(other)["chain"], "ethereum")

    def test_the_address_is_matched_whatever_its_case(self):
        bridge("CHNF", "ethereum", self.token.contract_address.lower())

        self.assertEqual(self._detail(self.token)["chain"], "ethereum")

    def test_a_switched_off_deployment_is_not_a_chain(self):
        bridge("CHNG", "base", self.token.contract_address, is_active=False)

        self.assertIsNone(self._detail(self.token)["chain"])

    def test_an_undeployed_token_has_no_address_no_chain_and_still_renders(self):
        payload = self._detail(self.draft)

        self.assertIsNone(payload["contractAddress"])
        self.assertIsNone(payload["chain"])
        self.assertEqual(payload["status"], "draft")

    def test_the_detail_key_set_is_pinned(self):
        bridge("CHNH", "base", self.token.contract_address)

        self.assertEqual(set(self._detail(self.token)), DETAIL_KEYS)
        self.assertEqual(set(self._detail(self.draft)), DETAIL_KEYS)

    def test_a_freshly_created_token_carries_the_chain_key(self):
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)

        response = self.client.post(
            "/api/v1/tokens/",
            {"company": str(self.tenant.company.uuid), "name": "New class", "symbol": "NEW", "totalSupply": "500"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), DETAIL_KEYS)
        self.assertIsNone(response.json()["chain"])
