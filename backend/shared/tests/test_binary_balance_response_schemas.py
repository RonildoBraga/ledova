import csv
import io
from types import SimpleNamespace
from unittest.mock import patch

from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase
from web3 import Web3

from feature_flags.models import FeatureFlag
from operators.models import Operator
from shared.tests.tenants import make_tenant
from tokens.services.share_token_service import ShareTokenService
from whitelist.models import WhitelistEntry

BALANCES_PATH = "/api/v1/trading/wallets/balances/"


class BinaryAndBalanceResponseSchemaTest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = SchemaGenerator().get_schema(request=None, public=True)

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.tenant = make_tenant("binary-balance-schema")
        self.client.force_authenticate(self.tenant.user)

    def resolved(self, schema):
        if "$ref" in schema:
            return self.resolved(self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]])
        return schema

    def response_content(self, path, response):
        self.assertEqual(response.status_code, 200)
        return self.document["paths"][path]["get"]["responses"]["200"].get("content", {})

    def wallet_balances(self, amount):
        service = ShareTokenService.__new__(ShareTokenService)
        service.chain_client = SimpleNamespace(
            is_valid_address=Web3.is_address, to_checksum_address=Web3.to_checksum_address
        )
        Operator.get().supported_settlement_assets.set([self.tenant.refs.stablecoin])
        with (
            patch("tokens.views.trading_wallet.ShareTokenService", return_value=service),
            patch.object(service, "_get_balance", return_value=amount),
        ):
            return self.client.get(BALANCES_PATH, {"wallet_address": self.tenant.wallet.address})

    def test_balances_schema_keeps_actual_nested_values_and_large_decimal_strings(self):
        amount = 9007199254740993
        response = self.wallet_balances(amount)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["walletAddress"], self.tenant.wallet.address)
        self.assertEqual(len(body["balances"]), 2)
        self.assertEqual({entry["type"] for entry in body["balances"]}, {"share_token", "stablecoin"})
        self.assertEqual({entry["balance"] for entry in body["balances"]}, {str(amount)})
        content = self.response_content(BALANCES_PATH, response)
        self.assertEqual(set(content), {"application/json"})
        schema = self.resolved(content["application/json"]["schema"])
        self.assertEqual(set(schema["properties"]), set(body))
        self.assertEqual(set(schema["required"]), set(body))
        self.assertEqual(schema["properties"]["walletAddress"]["type"], "string")
        self.assertEqual(schema["properties"]["balances"]["type"], "array")
        item = self.resolved(schema["properties"]["balances"]["items"])
        expected_types = {
            "token": "string",
            "symbol": "string",
            "name": "string",
            "balance": "string",
            "contractAddress": "string",
            "decimals": "integer",
            "type": "string",
        }
        self.assertEqual(set(item["properties"]), set(expected_types))
        self.assertEqual(set(item["required"]), set(expected_types))
        for entry in body["balances"]:
            self.assertEqual(set(entry), set(expected_types))
            for field, kind in expected_types.items():
                self.assertEqual(self.resolved(item["properties"][field])["type"], kind)
                self.assertIs(type(entry[field]), int if kind == "integer" else str)
        self.assertEqual(set(self.resolved(item["properties"]["type"])["enum"]), {"share_token", "stablecoin"})

    def test_balances_schema_keeps_an_empty_array_and_the_required_query(self):
        response = self.wallet_balances(0)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"walletAddress": self.tenant.wallet.address, "balances": []})
        content = self.response_content(BALANCES_PATH, response)
        self.assertIn("application/json", content)
        parameters = self.document["paths"][BALANCES_PATH]["get"].get("parameters", [])
        query = [entry for entry in parameters if entry["in"] == "query" and entry["name"] == "wallet_address"]
        self.assertEqual(len(query), 1)
        self.assertIs(query[0]["required"], True)
        self.assertEqual(query[0]["schema"]["type"], "string")

    @patch("tokens.views.trading_wallet.ShareTokenService")
    def test_balances_missing_foreign_and_anonymous_wallets_never_call_the_chain(self, service):
        self.assertEqual(self.client.get(BALANCES_PATH).status_code, 400)
        other = make_tenant("foreign-balance-schema")
        self.assertEqual(self.client.get(BALANCES_PATH, {"wallet_address": other.wallet.address}).status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(BALANCES_PATH, {"wallet_address": self.tenant.wallet.address}).status_code, 401
        )
        service.assert_not_called()

    def assert_file_schema(self, path, url, expected_bytes):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(b"".join(response.streaming_content), expected_bytes)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.closed)
        content = self.response_content(path, response)
        self.assertEqual(set(content), {"*/*"})
        self.assertEqual(content["*/*"]["schema"], {"type": "string", "format": "binary"})

    def test_personal_document_schema_describes_the_streamed_file(self):
        self.assert_file_schema(
            "/api/v1/documents/{uuid}/file/",
            f"/api/v1/documents/{self.tenant.document.uuid}/file/",
            f"payslip for {self.tenant.label}".encode(),
        )

    def test_company_document_schema_describes_the_streamed_file(self):
        self.assert_file_schema(
            "/api/v1/companies/{company_uuid}/documents/{uuid}/file/",
            f"/api/v1/companies/{self.tenant.company.uuid}/documents/{self.tenant.company_document.uuid}/file/",
            f"asic extract for {self.tenant.label}".encode(),
        )

    def test_classification_schema_describes_the_streamed_evidence(self):
        self.assert_file_schema(
            "/api/investor-classifications/{uuid}/evidence/",
            f"/api/investor-classifications/{self.tenant.investor_classification.uuid}/evidence/",
            f"evidence for {self.tenant.label}".encode(),
        )

    def test_file_media_remains_selected_from_storage_with_a_binary_fallback(self):
        document = self.tenant.document
        for mime in ("image/png", ""):
            document.mime_type = mime
            document.save(update_fields=["mime_type"])
            response = self.client.get(f"/api/v1/documents/{document.uuid}/file/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], mime or "application/octet-stream")
            self.assertEqual(b"".join(response.streaming_content), f"payslip for {self.tenant.label}".encode())
            self.assertTrue(response.closed)

    def assert_csv_schema(self, path, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        content = self.response_content(path, response)
        self.assertEqual(set(content), {"text/csv"})
        self.assertEqual(content["text/csv"]["schema"], {"type": "string"})

    @patch("tokens.views.share_token.export_rows", return_value=[["synthetic holder", "10"]])
    def test_register_export_schema_describes_csv_with_the_existing_rows(self, export):
        response = self.client.get(f"/api/v1/tokens/{self.tenant.deployed_token.uuid}/register/export/")
        self.assert_csv_schema("/api/v1/tokens/{uuid}/register/export/", response)
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode())))[1], ["synthetic holder", "10"])
        export.assert_called_once_with(self.tenant.deployed_token, self.tenant.user)

    def test_whitelist_export_schema_describes_the_actual_csv(self):
        self.tenant.user.is_staff = True
        self.tenant.user.save(update_fields=["is_staff"])
        WhitelistEntry.objects.create(wallet=self.tenant.wallet)
        response = self.client.get("/api/v1/whitelist/export/")
        self.assert_csv_schema("/api/v1/whitelist/export/", response)
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode())))[1][0], self.tenant.wallet.address)
