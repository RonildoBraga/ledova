from decimal import Decimal

from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase

from assets.models import ExchangeRate
from portfolios.tests.test_live_authorization import PortfolioFixtureMixin


class AssetAndPortfolioActionSchemaTest(PortfolioFixtureMixin, APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = SchemaGenerator().get_schema(request=None, public=True)

    def setUp(self):
        self.user, _, self.account, self.portfolio, self.wallet = self.make_tenant("alice")
        self.client.force_authenticate(self.user)
        ExchangeRate.objects.create(base_currency="USD", target_currency="AUD", rate=Decimal("1.25"))

    def resolve_schema(self, schema):
        if "$ref" in schema:
            return self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
        return schema

    def response_schema(self, path, method):
        schema = self.document["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
        return self.resolve_schema(schema)

    def assert_object_schema(self, schema, body, field_types):
        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["properties"]), set(body))
        self.assertEqual(
            {name: self.resolve_schema(field)["type"] for name, field in schema["properties"].items()},
            field_types,
        )

    def test_exchange_rate_schema_matches_the_rendered_decimal_text(self):
        response = self.client.get("/api/assets/exchange-rates/", {"currency": "aud"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body, {"baseCurrency": "USD", "targetCurrency": "AUD", "rate": "1.2500000000"})
        schema = self.response_schema("/api/assets/exchange-rates/", "get")
        self.assert_object_schema(
            schema, body, {"baseCurrency": "string", "targetCurrency": "string", "rate": "string"}
        )
        self.assertEqual(set(schema["required"]), set(body))

    def test_identity_rate_keeps_its_original_string_representation(self):
        response = self.client.get("/api/assets/exchange-rates/", {"currency": "usd"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"baseCurrency": "USD", "targetCurrency": "USD", "rate": "1"})

    def test_missing_and_anonymous_exchange_rate_requests_still_refuse(self):
        available = self.client.get("/api/assets/exchange-rates/")
        self.assertEqual(available.status_code, 200)
        self.assertEqual(available.json()["targetCurrency"], "AUD")

        missing = self.client.get("/api/assets/exchange-rates/", {"currency": "nzd"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json(), {"detail": "Exchange rate for USD→NZD not available"})

        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/assets/exchange-rates/").status_code, 401)

    def wallet_action(self, action):
        return self.client.post(
            f"/api/portfolios/{self.portfolio.uuid}/{action}/",
            {"walletUuid": str(self.wallet.uuid)},
            format="json",
        )

    def assert_wallet_response(self, response, action, expected_wallets, message):
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["success"], True)
        self.assertEqual(body["message"], message)
        portfolio = body["portfolio"]
        self.assertEqual(portfolio["uuid"], str(self.portfolio.uuid))
        self.assertEqual(portfolio["userAccount"], str(self.account.uuid))
        self.assertEqual(portfolio["name"], "Alice Portfolio")
        self.assertIs(portfolio["isActive"], True)
        self.assertEqual(portfolio["walletUuids"], expected_wallets)
        self.assertEqual(portfolio["walletCount"], len(expected_wallets))
        self.assertIs(type(portfolio["walletCount"]), int)
        self.assertIsInstance(portfolio["createdAt"], str)
        self.assertIsInstance(portfolio["updatedAt"], str)

        schema = self.response_schema(f"/api/portfolios/{{uuid}}/{action}/", "post")
        self.assert_object_schema(schema, body, {"success": "boolean", "message": "string", "portfolio": "object"})
        self.assertEqual(set(schema["required"]), set(body))
        nested = self.resolve_schema(schema["properties"]["portfolio"])
        self.assert_object_schema(
            nested,
            portfolio,
            {
                "uuid": "string",
                "userAccount": "string",
                "name": "string",
                "isActive": "boolean",
                "walletUuids": "array",
                "walletCount": "integer",
                "createdAt": "string",
                "updatedAt": "string",
            },
        )
        self.assertEqual(nested["properties"]["walletUuids"]["items"]["type"], "string")
        self.assertTrue({"walletUuids", "walletCount"}.issubset(nested["required"]))

    def test_add_wallet_schema_matches_the_populated_success_envelope(self):
        response = self.wallet_action("add-wallet")

        self.assert_wallet_response(
            response, "add-wallet", [str(self.wallet.uuid)], "Wallet added to portfolio successfully"
        )
        self.assertTrue(self.portfolio.wallets.filter(pk=self.wallet.pk).exists())

    def test_remove_wallet_schema_matches_the_empty_success_envelope(self):
        added = self.wallet_action("add-wallet")
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json()["portfolio"]["walletUuids"], [str(self.wallet.uuid)])
        self.assertEqual(added.json()["portfolio"]["walletCount"], 1)

        response = self.wallet_action("remove-wallet")

        self.assert_wallet_response(response, "remove-wallet", [], "Wallet removed from portfolio successfully")
        self.assertFalse(self.portfolio.wallets.filter(pk=self.wallet.pk).exists())
