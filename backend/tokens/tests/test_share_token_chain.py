from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment, AssetType
from companies.models import Company, CompanyStatus
from shared.constants import BLOCKCHAIN_BASE, BLOCKCHAIN_ETHEREUM
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken, ShareTokenStatus
from tokens.services.share_token_service import SHARE_ASSET_CHAIN, ShareTokenService

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

    def test_a_deployed_token_reports_the_chain_it_was_deployed_to(self):
        payload = self._detail(self.token)

        self.assertEqual(payload["chain"], BLOCKCHAIN_BASE)
        self.assertEqual(payload["contractAddress"], self.token.contract_address)

    def test_the_chain_survives_a_deployment_that_never_bridged_into_an_asset(self):
        self.assertFalse(AssetChainDeployment.objects.filter(contract_address=self.token.contract_address).exists())

        self.assertEqual(self._detail(self.token)["chain"], BLOCKCHAIN_BASE)

    def test_a_switched_off_asset_deployment_does_not_take_the_chain_away(self):
        bridge("CHNG", BLOCKCHAIN_BASE, self.token.contract_address, is_active=False)

        self.assertEqual(self._detail(self.token)["chain"], BLOCKCHAIN_BASE)

    def test_the_same_address_on_another_chain_does_not_move_the_token(self):
        bridge("CHNI", BLOCKCHAIN_ETHEREUM, self.token.contract_address)
        bridge("CHNJ", BLOCKCHAIN_BASE, self.token.contract_address)

        self.assertEqual(self._detail(self.token)["chain"], BLOCKCHAIN_BASE)

    def test_a_token_deployed_off_base_reports_its_own_chain(self):
        other = self.tenant.company.tokens.create(
            name="Second class",
            symbol="SEC",
            total_supply="10",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + "2" * 40,
            chain=BLOCKCHAIN_ETHEREUM,
        )

        self.assertEqual(self._detail(other)["chain"], BLOCKCHAIN_ETHEREUM)
        self.assertEqual(self._detail(self.token)["chain"], BLOCKCHAIN_BASE)

    def test_an_undeployed_token_has_no_address_no_chain_and_still_renders(self):
        payload = self._detail(self.draft)

        self.assertIsNone(payload["contractAddress"])
        self.assertIsNone(payload["chain"])
        self.assertEqual(payload["status"], "draft")

    def test_the_detail_key_set_is_pinned(self):
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

    def test_the_client_cannot_choose_the_chain(self):
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)

        response = self.client.post(
            "/api/v1/tokens/",
            {
                "company": str(self.tenant.company.uuid),
                "name": "Chosen chain",
                "symbol": "CHS",
                "totalSupply": "500",
                "chain": BLOCKCHAIN_ETHEREUM,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(ShareToken.objects.get(symbol="CHS").chain)


class DeploymentWritesTheChainTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("deploychain")
        self.token = self.tenant.token

    def test_finishing_a_deployment_records_the_chain_the_deployer_used(self):
        address = "0x" + "9" * 40
        with patch.object(ShareTokenService, "__init__", lambda self: None), patch.object(
            ShareTokenService, "bridge_share_asset"
        ), patch.object(ShareTokenService, "_approve_for_swap"):
            ShareTokenService()._finish_deployment(self.token, address)

        self.token.refresh_from_db()
        self.assertEqual(self.token.status, ShareTokenStatus.DEPLOYED)
        self.assertEqual(self.token.contract_address, address)
        self.assertEqual(self.token.chain, SHARE_ASSET_CHAIN)

    def test_the_chain_is_recorded_even_when_the_asset_bridge_fails(self):
        address = "0x" + "8" * 40
        with patch.object(ShareTokenService, "__init__", lambda self: None), patch.object(
            ShareTokenService, "get_token_by_identifier", side_effect=RuntimeError("no factory")
        ), patch.object(ShareTokenService, "_approve_for_swap"):
            ShareTokenService()._finish_deployment(self.token, address)

        self.token.refresh_from_db()
        self.assertFalse(AssetChainDeployment.objects.filter(contract_address=address).exists())
        self.assertEqual(self.token.chain, SHARE_ASSET_CHAIN)


class ChainBackfillTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("backfill")
        self.backfill = import_module("tokens.migrations.0017_share_token_chain").set_chain_of_deployed_tokens

    def test_tokens_deployed_before_the_column_existed_are_backfilled_to_base(self):
        ShareToken.objects.update(chain=None)

        self.backfill(apps, None)

        self.assertEqual(ShareToken.objects.get(pk=self.tenant.deployed_token.pk).chain, BLOCKCHAIN_BASE)
        self.assertIsNone(ShareToken.objects.get(pk=self.tenant.token.pk).chain)

    def test_the_backfill_leaves_a_token_with_an_empty_address_alone(self):
        ShareToken.objects.filter(pk=self.tenant.token.pk).update(chain=None, contract_address="")

        self.backfill(apps, None)

        self.assertIsNone(ShareToken.objects.get(pk=self.tenant.token.pk).chain)
