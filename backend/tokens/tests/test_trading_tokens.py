from uuid import uuid4

from rest_framework.test import APITestCase

from shared.tests.tenants import make_eligible, make_tenant, open_to_investors

TRADING = "/api/v1/trading/tokens/"
DIRECTORY = "/api/v1/directory/tokens/"


class TradingMarketScopeTest(APITestCase):
    def setUp(self):
        self.holder = make_tenant("holder")
        self.issuer = make_tenant("issuer")
        self.client.force_authenticate(self.holder.user)

    def _uuids(self, path):
        return {row["uuid"] for row in self.client.get(path).json()["results"]}

    def test_the_market_does_not_wait_for_the_issuer_to_opt_into_the_directory(self):
        make_eligible(self.holder)
        self.assertIn(str(self.issuer.deployed_token.uuid), self._uuids(TRADING))
        self.assertEqual(self._uuids(DIRECTORY), set())
        self.assertEqual(self.client.get(f"{TRADING}{self.issuer.deployed_token.uuid}/").status_code, 200)
        self.assertEqual(self.client.get(f"{DIRECTORY}{self.issuer.deployed_token.uuid}/").status_code, 404)

    def test_the_issuers_own_owner_sees_the_market_for_its_share_class(self):
        make_eligible(self.issuer)
        self.client.force_authenticate(self.issuer.user)
        self.assertIn(str(self.issuer.deployed_token.uuid), self._uuids(TRADING))

    def test_the_directory_adds_the_share_class_once_the_issuer_opts_in(self):
        make_eligible(self.holder)
        open_to_investors(self.issuer)
        self.assertIn(str(self.issuer.deployed_token.uuid), self._uuids(DIRECTORY))
        self.assertIn(str(self.issuer.deployed_token.uuid), self._uuids(TRADING))

    def test_an_undeployed_share_class_is_never_in_the_market(self):
        make_eligible(self.holder)
        self.assertNotIn(str(self.issuer.token.uuid), self._uuids(TRADING))

    def test_an_ineligible_caller_gets_an_empty_market_and_a_phantom_404(self):
        self.assertEqual(self._uuids(TRADING), set())
        real = self.client.get(f"{TRADING}{self.issuer.deployed_token.uuid}/")
        phantom = self.client.get(f"{TRADING}{uuid4()}/")
        self.assertEqual((real.status_code, phantom.status_code), (404, 404))
        self.assertEqual(real.content, phantom.content)

    def test_the_market_actions_answer_the_eligible_and_hide_from_the_rest(self):
        for suffix in ("market-data", "order-book"):
            with self.subTest(suffix=suffix):
                path = f"{TRADING}{self.issuer.deployed_token.uuid}/{suffix}/"
                real = self.client.get(path)
                phantom = self.client.get(f"{TRADING}{uuid4()}/{suffix}/")
                self.assertEqual((real.status_code, phantom.status_code), (404, 404))
                self.assertEqual(real.content, phantom.content)
        make_eligible(self.holder)
        for suffix in ("market-data", "order-book"):
            with self.subTest(suffix=suffix, eligible=True):
                path = f"{TRADING}{self.issuer.deployed_token.uuid}/{suffix}/"
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_the_directory_carries_no_market_action(self):
        make_eligible(self.holder)
        open_to_investors(self.issuer)
        for suffix in ("market-data", "order-book"):
            with self.subTest(suffix=suffix):
                path = f"{DIRECTORY}{self.issuer.deployed_token.uuid}/{suffix}/"
                self.assertEqual(self.client.get(path).status_code, 404)
