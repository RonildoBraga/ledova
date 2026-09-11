from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator
from jsonschema import Draft4Validator
from rest_framework.test import APIClient

from authentication.services import TokenService
from authentication.tests.test_legacy_auth_protocol import LegacyAuthProtocolTestCase


class AuthSchemaTest(LegacyAuthProtocolTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        GENERATOR_STATS.reset()
        diagnostics = StringIO()
        with redirect_stderr(diagnostics):
            cls.document = SchemaGenerator().get_schema(request=None, public=True)
        cls.diagnostics = diagnostics.getvalue()

    def resolved(self, schema):
        if isinstance(schema, list):
            return [self.resolved(value) for value in schema]
        if not isinstance(schema, dict):
            return schema
        if "$ref" in schema:
            return self.resolved(self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]])
        result = {key: self.resolved(value) for key, value in schema.items() if key != "nullable"}
        if schema.get("nullable") and "type" in result:
            return {"anyOf": [result, {"type": "null"}]}
        return result

    def request_schema(self, path):
        operation = self.document["paths"][path]["post"]
        self.assertIn("requestBody", operation, path)
        return self.resolved(operation["requestBody"]["content"]["application/json"]["schema"])

    def response_validator(self, path, response, method="post"):
        operation = self.document["paths"][path][method]
        code = str(response.status_code)
        self.assertIn(code, operation["responses"], response.content)
        schema = self.resolved(operation["responses"][code]["content"]["application/json"]["schema"])
        validator = Draft4Validator(schema)
        self.assertEqual(list(validator.iter_errors(response.json())), [], response.content)
        return validator

    def cookie_client(self, user):
        access, refresh = TokenService.issue(user)
        client = APIClient(enforce_csrf_checks=True)
        client.cookies[settings.AUTH_COOKIE["access"]] = access
        client.cookies[settings.AUTH_COOKIE["refresh"]] = refresh
        verify = client.get("/api/auth/verify/")
        self.assertEqual(verify.status_code, 200, verify.content)
        self.assertTrue(verify.json()["valid"])
        return client, client.cookies[settings.CSRF_COOKIE_NAME].value

    def test_validated_requests_declare_the_actual_required_camel_case_fields(self):
        cases = {
            "/api/signup/": {"email", "password", "passwordConfirm"},
            "/api/signin/": {"email", "password"},
            "/api/email-verification/": {"email", "token"},
            "/api/change-password/": {"currentPassword", "newPassword", "newPasswordConfirm"},
            "/api/resend-verification/": set(),
        }
        for path, required in cases.items():
            with self.subTest(path=path):
                schema = self.request_schema(path)
                self.assertEqual(set(schema.get("required", ())), required)
                self.assertEqual(set(schema["properties"]), required or {"email"})
                body = self.document["paths"][path]["post"]["requestBody"]
                self.assertEqual(body.get("required", False), bool(required))
                for field in required:
                    if "password" in field.lower():
                        self.assertTrue(schema["properties"][field]["writeOnly"])

    def test_signup_declares_the_created_identity_and_preserves_input_validation(self):
        path = "/api/signup/"
        payload = {"email": "schema-new@example.test", "password": self.password, "passwordConfirm": self.password}
        with patch("authentication.views.user.EmailCodeService.send") as send:
            invalid = self.client.post(path, {"email": payload["email"]}, format="json")
            self.assertEqual(invalid.status_code, 400, invalid.content)
            send.assert_not_called()
            response = self.client.post(path, payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        send.assert_called_once()
        self.response_validator(path, response)
        self.assertNotIn("200", self.document["paths"][path]["post"]["responses"])
        self.assertTrue(Draft4Validator(self.request_schema(path)).is_valid(payload))
        self.assertFalse(Draft4Validator(self.request_schema(path)).is_valid({"email": payload["email"]}))

    def test_signin_declares_the_real_cookie_and_bearer_session_bodies(self):
        user = self.create_completed_user()
        path = "/api/signin/"
        for transport in ("cookie", "bearer"):
            with self.subTest(transport=transport):
                client = APIClient()
                response = client.post(
                    path,
                    {"email": user.email, "password": self.password},
                    format="json",
                    HTTP_X_AUTH_TRANSPORT=transport,
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.response_validator(path, response)
                if transport == "cookie":
                    self.assertIn(settings.AUTH_COOKIE["access"], response.cookies)
                    self.assertNotIn("tokens", response.json())
                else:
                    self.assertEqual(set(response.json()["tokens"][0]), {"accessToken", "refreshToken"})
                    self.assertEqual(list(response.cookies), [])

    def test_email_verification_uses_the_same_token_pair_component_as_signin(self):
        user = self.create_user(verified=False)
        path = "/api/email-verification/"
        for transport in ("cookie", "bearer"):
            with self.subTest(transport=transport):
                client = APIClient()
                with patch("authentication.views.user.EmailCodeService.verify", return_value=True):
                    response = client.post(
                        path,
                        {"email": user.email, "token": "123456"},
                        format="json",
                        HTTP_X_AUTH_TRANSPORT=transport,
                    )
                self.assertEqual(response.status_code, 200, response.content)
                self.response_validator(path, response)
                self.assertEqual("tokens" in response.json(), transport == "bearer")
        schemas = self.document["components"]["schemas"]
        pair = schemas["AuthSession"]["properties"]["tokens"]["items"]
        self.assertEqual(pair, schemas["AuthEmailVerified"]["properties"]["tokens"]["items"])
        self.assertNotIn("Encountered 2 components with identical names", self.diagnostics)

    def test_cookie_refresh_requires_csrf_and_declares_its_message_response(self):
        path = "/api/token/refresh/"
        client, csrf = self.cookie_client(self.create_completed_user())
        refused = client.post(path, {}, format="json")
        self.assertEqual(refused.status_code, 403, refused.content)
        response = client.post(path, {}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"message": "Session refreshed."})
        self.assertIn(settings.AUTH_COOKIE["access"], response.cookies)
        validator = self.response_validator(path, response)
        self.assertFalse(validator.is_valid({}))
        self.assertTrue(Draft4Validator(self.request_schema(path)).is_valid({}))
        self.assertFalse(self.document["paths"][path]["post"]["requestBody"].get("required", False))

    def test_bearer_refresh_declares_its_real_body_and_needs_no_cookie(self):
        path = "/api/token/refresh/"
        _, refresh = TokenService.issue(self.create_completed_user())
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(path, {"refresh": refresh}, format="json", HTTP_X_AUTH_TRANSPORT="bearer")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()), {"access", "refresh"})
        self.assertEqual(list(response.cookies), [])
        validator = self.response_validator(path, response)
        self.assertFalse(validator.is_valid({"access": response.json()["access"]}))
        self.assertTrue(Draft4Validator(self.request_schema(path)).is_valid({"refresh": refresh}))

    def test_refresh_metadata_keeps_falsy_body_values_that_fall_back_to_the_cookie(self):
        path = "/api/token/refresh/"
        user = self.create_completed_user()
        for value in (None, "", False, 0, [], {}):
            with self.subTest(value=value):
                client, csrf = self.cookie_client(user)
                response = client.post(path, {"refresh": value}, format="json", HTTP_X_CSRFTOKEN=csrf)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json(), {"message": "Session refreshed."})
                self.assertTrue(Draft4Validator(self.request_schema(path)).is_valid({"refresh": value}))

    def test_refresh_declares_the_missing_and_invalid_token_responses(self):
        path = "/api/token/refresh/"
        for body, expected in (({}, 400), ({"refresh": "not-a-refresh-token"}, 401)):
            with self.subTest(status=expected):
                response = self.client.post(path, body, format="json", HTTP_X_AUTH_TRANSPORT="bearer")
                self.assertEqual(response.status_code, expected, response.content)
                self.response_validator(path, response)

    def test_logout_bodies_remain_optional_and_all_sessions_needs_no_body(self):
        user = self.create_completed_user()
        for path in ("/api/signout/", "/api/signout-all/"):
            with self.subTest(path=path):
                access, _ = TokenService.issue(user)
                client = APIClient(enforce_csrf_checks=True)
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
                response = client.post(path)
                self.assertEqual(response.status_code, 200, response.content)
                self.response_validator(path, response)
        path = "/api/signout/"
        self.assertTrue(Draft4Validator(self.request_schema(path)).is_valid({}))
        self.assertFalse(self.document["paths"][path]["post"]["requestBody"].get("required", False))
        self.assertNotIn("requestBody", self.document["paths"]["/api/signout-all/"]["post"])

    def test_resend_email_is_optional_only_when_the_request_is_authenticated(self):
        path = "/api/resend-verification/"
        user = self.create_completed_user(verified=False)
        with patch("authentication.views.user.EmailCodeService.send") as send:
            refused = self.client.post(path, {}, format="json")
            self.assertEqual(refused.status_code, 400, refused.content)
            send.assert_not_called()
            explicit = self.client.post(path, {"email": user.email}, format="json")
            self.assertEqual(explicit.status_code, 200, explicit.content)
            self.response_validator(path, explicit)
            send.assert_called_once_with(user)
            access, _ = TokenService.issue(user)
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
            implicit = self.client.post(path, {}, format="json")
            self.assertEqual(implicit.status_code, 200, implicit.content)
            self.response_validator(path, implicit)
            self.assertEqual(send.call_count, 2)
        self.assertIn("Anonymous requests must include email", self.document["paths"][path]["post"]["description"])

    def test_transport_header_is_optional_and_does_not_advertise_a_cookie_only_enum(self):
        for path in ("/api/signin/", "/api/email-verification/", "/api/token/refresh/", "/api/signout/"):
            with self.subTest(path=path):
                parameters = self.document["paths"][path]["post"].get("parameters", [])
                transport = next((item for item in parameters if item["name"] == "X-Auth-Transport"), None)
                self.assertIsNotNone(transport)
                self.assertEqual(transport["in"], "header")
                self.assertFalse(transport.get("required", False))
                self.assertNotIn("enum", transport["schema"])
                self.assertIn("bearer", transport["description"])

    def test_security_declares_bearer_or_cookie_and_only_public_routes_allow_anonymous(self):
        schemes = self.document["components"].get("securitySchemes", {})
        self.assertIn("bearerAuth", schemes)
        self.assertEqual(schemes["bearerAuth"]["type"], "http")
        self.assertEqual(schemes["bearerAuth"]["scheme"], "bearer")
        self.assertEqual(schemes["cookieAuth"]["type"], "apiKey")
        self.assertEqual(schemes["cookieAuth"]["in"], "cookie")
        self.assertEqual(schemes["cookieAuth"]["name"], settings.AUTH_COOKIE["access"])
        self.assertIn("CSRF", schemes["cookieAuth"]["description"])
        alternatives = [{"bearerAuth": []}, {"cookieAuth": []}]
        self.assertCountEqual(self.document["paths"]["/api/change-password/"]["post"]["security"], alternatives)
        self.assertCountEqual(self.document["paths"]["/api/signin/"]["post"]["security"], [*alternatives, {}])
        self.assertNotIn("could not resolve authenticator", self.diagnostics)
        self.assertNotIn("unable to guess serializer", self.diagnostics)

    def test_cookie_security_uses_the_configured_cookie_name_and_matches_live_authentication(self):
        cookie_settings = {**settings.AUTH_COOKIE, "access": "schema_access_cookie"}
        with override_settings(AUTH_COOKIE=cookie_settings):
            GENERATOR_STATS.reset()
            with redirect_stderr(StringIO()):
                document = SchemaGenerator().get_schema(request=None, public=True)
            access, _ = TokenService.issue(self.create_completed_user())
            client = APIClient()
            anonymous = client.get("/api/auth/verify/")
            self.assertFalse(anonymous.json()["valid"])
            client.cookies[cookie_settings["access"]] = access
            authenticated = client.get("/api/auth/verify/")
            self.assertTrue(authenticated.json()["valid"])
            self.assertEqual(document["components"]["securitySchemes"]["cookieAuth"]["name"], cookie_settings["access"])
