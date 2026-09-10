from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import Mock, patch

from django.test import override_settings
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from integrations.kycaid.client import KYCAIDService
from integrations.sumsub.client import SumSubService
from integrations.transak.client import TransakClient
from shared.tests.tenants import make_tenant
from tokens.tests.test_signed_transactions import SIGNER, sign_legacy
from users.models import UserProfile
from wallets.models import Wallet

FIAT = "/api/fiat-purchases/transak-widget-url/"
IDENTITY = "/api/users/identity-verification/"
TRANSFERS = "/api/v1/trading/transfers/"


@override_settings(ATOMIC_SWAP_ADDRESS="0x" + "8" * 40)
class RequestViewSchemaTest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        GENERATOR_STATS.reset()
        diagnostics = StringIO()
        with redirect_stderr(diagnostics):
            cls.document = SchemaGenerator().get_schema(request=None, public=True)
        cls.diagnostics = diagnostics.getvalue()

    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.owner = make_tenant("request-view-schema")
        self.client.force_authenticate(self.owner.user)

    def resolved(self, schema):
        if "$ref" in schema:
            return self.resolved(self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]])
        return schema

    def request_schema(self, path):
        operation = self.document["paths"][path]["post"]
        self.assertIn("requestBody", operation, path)
        return self.resolved(operation["requestBody"]["content"]["application/json"]["schema"])

    def response_schema(self, path, method="post"):
        return self.resolved(
            self.document["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
        )

    def widget(self, payload):
        provider = object.__new__(TransakClient)
        provider.api_key = "synthetic-widget-id"
        provider.referrer_domain = "https://app.example.test"
        provider.api_gateway_url = "https://gateway.example.test"
        provider._get_access_token = Mock(return_value="synthetic-widget-session")
        reply = Mock(status_code=200)
        reply.json.return_value = {"data": {"widgetUrl": "https://widget.example.test/synthetic"}}
        with (
            patch("wallets.services.fiat_onramp.TransakClient", return_value=provider),
            patch("integrations.transak.client.requests.post", return_value=reply) as send,
        ):
            response = self.client.post(FIAT, payload, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        send.assert_called_once()
        return response.json(), send.call_args.kwargs["json"]["widgetParams"]

    def assert_nullable_response(self, path, body, fields, method="post"):
        schema = self.response_schema(path, method)
        self.assertEqual(set(schema["properties"]), set(body))
        self.assertTrue(set(schema.get("required", ())).issubset(body))
        for field in fields:
            with self.subTest(field=field):
                self.assertIsNone(body[field])
                self.assertTrue(self.resolved(schema["properties"][field]).get("nullable"), field)

    def test_default_widget_request_declares_its_actual_inputs_without_accepting_client_ownership(self):
        payload = {"walletUuid": str(self.owner.wallet.uuid)}
        body, sent = self.widget(payload)
        self.assertEqual(sent["defaultFiatCurrency"], "AUD")
        self.assertEqual(sent["walletAddress"], self.owner.wallet.address)
        self.assertEqual(sent["email"], self.owner.user.email)
        self.assertEqual(sent["partnerCustomerId"], str(self.owner.user.pk))
        self.assertEqual(sent["productsAvailed"], "BUY")
        self.assertTrue(sent["disableWalletAddressForm"])
        self.assertEqual(body["cryptoCurrency"], sent["cryptoCurrencyCode"])
        schema = self.request_schema(FIAT)
        self.assertEqual(schema["required"], ["walletUuid"])
        self.assertEqual(
            set(schema["properties"]),
            {
                "walletUuid",
                "cryptoCurrencyCode",
                "fiatCurrency",
                "defaultFiatCurrency",
                "fiatAmount",
                "defaultFiatAmount",
                "themeColor",
                "redirectUrl",
            },
        )
        self.assertEqual(schema["properties"]["walletUuid"]["type"], "string")
        self.assertNotIn("format", schema["properties"]["walletUuid"])
        self.assertEqual(schema["properties"]["defaultFiatCurrency"]["default"], sent["defaultFiatCurrency"])
        self.assertEqual(set(self.response_schema(FIAT)["properties"]), set(body))

    def test_widget_amount_metadata_preserves_real_number_string_and_boolean_coercion(self):
        for amount, expected in ((125.75, "125"), ("250.5", "250"), (True, "1")):
            with self.subTest(amount=amount):
                body, sent = self.widget(
                    {
                        "walletUuid": str(self.owner.wallet.uuid),
                        "fiatAmount": amount,
                        "defaultFiatAmount": amount,
                        "fiatCurrency": "usd",
                        "defaultFiatCurrency": "eur",
                        "cryptoCurrencyCode": "eth",
                    }
                )
                self.assertEqual(sent["fiatAmount"], expected)
                self.assertEqual(sent["defaultFiatAmount"], expected)
                self.assertEqual(sent["fiatCurrency"], "USD")
                self.assertEqual(sent["defaultFiatCurrency"], "EUR")
                self.assertEqual(body["cryptoCurrency"], "eth")
                schema = self.request_schema(FIAT)
                for field in ("fiatAmount", "defaultFiatAmount"):
                    kinds = {branch["type"] for branch in schema["properties"][field]["oneOf"]}
                    self.assertEqual(kinds, {"number", "string", "boolean"})

    def test_widget_nulls_and_zero_keep_the_existing_default_and_omission_rules(self):
        for amount in (None, 0, False, ""):
            with self.subTest(amount=amount):
                body, sent = self.widget(
                    {
                        "walletUuid": str(self.owner.wallet.uuid),
                        "fiatAmount": amount,
                        "defaultFiatAmount": amount,
                        "fiatCurrency": None,
                        "defaultFiatCurrency": None,
                        "cryptoCurrencyCode": None,
                    }
                )
                for field in ("fiatAmount", "defaultFiatAmount", "fiatCurrency", "defaultFiatCurrency"):
                    self.assertNotIn(field, sent)
                    declared = self.request_schema(FIAT)["properties"][field]
                    variants = declared.get("oneOf", [declared])
                    self.assertTrue(any(variant.get("nullable") for variant in variants))
                self.assertEqual(body["cryptoCurrency"], sent["cryptoCurrencyCode"])

    def test_widget_pass_through_metadata_does_not_invent_url_or_theme_validation(self):
        values = {"redirectUrl": {"returnTo": "profile"}, "themeColor": ["synthetic"]}
        _, sent = self.widget({"walletUuid": str(self.owner.wallet.uuid), **values})
        self.assertEqual(sent["redirectURL"], {"return_to": "profile"})
        self.assertEqual(sent["themeColor"], values["themeColor"])
        for field in values:
            self.assertEqual(self.request_schema(FIAT)["properties"][field], {"nullable": True})

    def test_widget_body_and_wallet_remain_required_by_the_actual_view(self):
        with patch("wallets.views.fiat_purchase.generate_transak_widget_url") as provider:
            for body in ({}, {"walletUuid": ""}):
                with self.subTest(body=body):
                    response = self.client.post(FIAT, body, format="json")
                    self.assertEqual(response.status_code, 400)
            provider.assert_not_called()
        self.request_schema(FIAT)
        self.assertTrue(self.document["paths"][FIAT]["post"]["requestBody"]["required"])

    def test_kycaid_session_requires_no_body_and_declares_its_absent_access_token(self):
        profile = UserProfile.objects.get(user=self.owner.user)
        profile.kyc_provider = "kycaid"
        profile.kycaid_applicant_id = "synthetic-applicant"
        profile.save(update_fields=["kyc_provider", "kycaid_applicant_id"])
        provider = object.__new__(KYCAIDService)
        provider.form_id = "synthetic-form"
        provider.get_form_url = Mock(return_value="https://form.example.test/verification")
        with patch("users.services.identity.get_kyc_provider", return_value=provider):
            response = self.client.post(IDENTITY + "token/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["provider"], "kycaid")
        self.assertEqual(body["applicantId"], profile.kycaid_applicant_id)
        self.assertEqual(body["formUrl"], provider.get_form_url.return_value)
        provider.get_form_url.assert_called_once_with(provider.form_id, profile.kycaid_applicant_id)
        self.assertNotIn("requestBody", self.document["paths"][IDENTITY + "token/"]["post"])
        self.assert_nullable_response(IDENTITY + "token/", body, ["accessToken"])

    def test_sumsub_session_declares_its_absent_form_url(self):
        profile = UserProfile.objects.get(user=self.owner.user)
        profile.kyc_provider = "sumsub"
        profile.sumsub_applicant_id = "synthetic-applicant"
        profile.save(update_fields=["kyc_provider", "sumsub_applicant_id"])
        provider = object.__new__(SumSubService)
        provider.generate_access_token_for_external_user = Mock(return_value="synthetic-form-token")
        with patch("users.services.identity.get_kyc_provider", return_value=provider):
            response = self.client.post(IDENTITY + "token/", {"applicantId": "ignored"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["applicantId"], profile.sumsub_applicant_id)
        self.assertEqual(body["accessToken"], provider.generate_access_token_for_external_user.return_value)
        provider.generate_access_token_for_external_user.assert_called_once_with(str(profile.uuid))
        self.assert_nullable_response(IDENTITY + "token/", body, ["formUrl"])

    def test_missing_sumsub_applicant_identity_remains_nullable_without_changing_creation(self):
        profile = UserProfile.objects.get(user=self.owner.user)
        profile.kyc_provider = "sumsub"
        profile.sumsub_applicant_id = None
        profile.save(update_fields=["kyc_provider", "sumsub_applicant_id"])
        provider = object.__new__(SumSubService)
        provider.create_applicant = Mock(return_value={})
        provider.generate_access_token_for_external_user = Mock(return_value="synthetic-form-token")
        with patch("users.services.identity.get_kyc_provider", return_value=provider):
            response = self.client.post(IDENTITY + "token/")
        self.assertEqual(response.status_code, 200, response.content)
        provider.create_applicant.assert_called_once()
        self.assertEqual(provider.create_applicant.call_args.args, (str(profile.uuid),))
        self.assertEqual(response.json()["accessToken"], provider.generate_access_token_for_external_user.return_value)
        self.assert_nullable_response(IDENTITY + "token/", response.json(), ["applicantId", "formUrl"])

    def test_unstarted_identity_status_declares_the_real_nullable_profile_state(self):
        profile = UserProfile.objects.get(user=self.owner.user)
        profile.kycaid_applicant_id = None
        profile.sumsub_applicant_id = None
        profile.verification_status = None
        profile.save(update_fields=["kycaid_applicant_id", "sumsub_applicant_id", "verification_status"])
        provider = Mock()
        with patch("users.services.identity.get_kyc_provider", return_value=provider):
            response = self.client.get(IDENTITY + "status/")
        self.assertEqual(response.status_code, 200, response.content)
        provider.get_applicant_status.assert_not_called()
        provider.get_applicant_data.assert_not_called()
        self.assert_nullable_response(IDENTITY + "status/", response.json(), ["status", "applicantId"], "get")

    def test_trading_prepare_request_describes_the_fields_the_real_route_validates(self):
        payload = {
            "token": str(self.owner.deployed_token.uuid),
            "fromAddress": self.owner.wallet.address,
            "toAddress": "0x" + "7" * 40,
            "amount": 12,
        }
        with patch("tokens.views.trading_transfer.TokenTransferService") as service:
            service.contract_address.return_value = self.owner.deployed_token.contract_address
            service.return_value.prepare_transfer.return_value = {}
            response = self.client.post(TRANSFERS + "prepare/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        service.return_value.prepare_transfer.assert_called_once_with(
            token=self.owner.deployed_token,
            from_address=self.owner.wallet.address,
            to_address=payload["toAddress"],
            amount=payload["amount"],
        )
        schema = self.request_schema(TRANSFERS + "prepare/")
        self.assertEqual(set(schema["properties"]), set(payload))
        self.assertEqual(set(schema["required"]), set(payload))
        self.assertEqual(schema["properties"]["token"]["format"], "uuid")
        self.assertEqual(schema["properties"]["amount"]["minimum"], 1)
        with patch("tokens.views.trading_transfer.TokenTransferService") as refused:
            response = self.client.post(TRANSFERS + "prepare/", {**payload, "amount": 0}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"amount"})
        refused.assert_not_called()

    def test_trading_broadcast_request_keeps_its_own_fields_and_the_wallet_contract(self):
        Wallet.objects.create(
            user_account=self.owner.account, address=SIGNER.address, chain="base", verification_status="VERIFIED"
        )
        signed = sign_legacy(to="0x" + "8" * 40)
        with patch("tokens.views.trading_transfer.TokenTransferService") as service:
            service.return_value.broadcast_transfer.return_value = ("0x" + "f" * 64, {"blockNumber": 7})
            response = self.client.post(TRANSFERS + "broadcast/", {"signedTransaction": signed}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        service.return_value.broadcast_transfer.assert_called_once_with(signed)
        schema = self.request_schema(TRANSFERS + "broadcast/")
        self.assertEqual(set(schema["properties"]), {"signedTransaction"})
        self.assertEqual(schema["required"], ["signedTransaction"])
        wallet = self.request_schema("/api/wallets/{uuid}/broadcast-transfer/")
        self.assertEqual(
            set(wallet["properties"]),
            {"signedTransaction", "toAddress", "amount", "transactionFee", "tokenContract"},
        )
        self.assertEqual(wallet["required"], ["signedTransaction"])

    def test_declared_views_no_longer_need_a_guessed_serializer(self):
        errors = [line.split(": Error ", 1)[1] for line in self.diagnostics.splitlines() if ": Error " in line]
        for name in ("FiatPurchaseViewSet", "IdentityVerificationViewSet", "TradingTransferViewSet"):
            with self.subTest(view=name):
                self.assertFalse(any(line.startswith(f"[{name}]") for line in errors), errors)
        for path in (FIAT, IDENTITY + "token/", TRANSFERS + "prepare/", TRANSFERS + "broadcast/"):
            self.assertIn("properties", self.response_schema(path))
