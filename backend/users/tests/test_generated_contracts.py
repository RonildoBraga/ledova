from copy import deepcopy

from drf_spectacular.generators import SchemaGenerator
from jsonschema import Draft4Validator
from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from users.models import UserProfile


class GeneratedClientContractTest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = SchemaGenerator().get_schema(request=None, public=True)

    def setUp(self):
        self.owner = make_tenant("generated-contract")
        self.client.force_authenticate(self.owner.user)

    def resolved(self, schema):
        if isinstance(schema, list):
            return [self.resolved(value) for value in schema]
        if not isinstance(schema, dict):
            return schema
        if "$ref" in schema:
            target = self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
            return self.resolved({**target, **{key: value for key, value in schema.items() if key != "$ref"}})
        result = {key: self.resolved(value) for key, value in schema.items() if key != "nullable"}
        return {"anyOf": [result, {"type": "null"}]} if schema.get("nullable") else result

    def request_schema(self, path, method="post"):
        return self.resolved(
            self.document["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
        )

    def assert_response(self, path, response, method="get"):
        self.assertLess(response.status_code, 300, response.content)
        schema = self.document["paths"][path][method]["responses"][str(response.status_code)]
        validator = Draft4Validator(self.resolved(schema["content"]["application/json"]["schema"]))
        self.assertEqual(list(validator.iter_errors(response.json())), [], response.content)
        return validator

    def test_singleton_lists_validate_the_object_and_reject_a_pagination_envelope(self):
        for path in ("/api/user-accounts/", "/api/user-preferences/", "/api/notification-preferences/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                validator = self.assert_response(path, response)
                self.assertIsInstance(response.json(), dict)
                self.assertFalse(validator.is_valid({"count": 1, "results": [response.json()]}))

    def test_selected_portfolio_is_a_uuid_input_and_nullable_object_output(self):
        path = "/api/user-preferences/"
        request = self.request_schema(path)
        field = Draft4Validator(request["properties"]["selectedPortfolio"])
        self.assertNotIn("userAccount", request["properties"])
        self.assertNotIn("userProfile", request["properties"])
        for value in (None, str(self.owner.portfolio.uuid)):
            with self.subTest(value=value):
                self.assertTrue(field.is_valid(value))
                response = self.client.post(path, {"selectedPortfolio": value}, format="json")
                self.assertEqual(response.status_code, 200, response.content)
                validator = self.assert_response(path, response, "post")
                body = response.json()
                if value is None:
                    self.assertIsNone(body["selectedPortfolio"])
                else:
                    self.assertEqual(body["selectedPortfolio"]["uuid"], value)
                    self.assertFalse(field.is_valid(body["selectedPortfolio"]))
                    self.assertFalse(validator.is_valid({**body, "selectedPortfolio": value}))

    def test_favourite_asset_keeps_a_uuid_request_and_a_nested_asset_response(self):
        path = "/api/favourite-assets/"
        request = self.request_schema(path)
        asset_id = str(self.owner.refs.stablecoin.uuid)
        self.assertTrue(Draft4Validator(request).is_valid({"asset": asset_id}))
        self.assertNotIn("uuid", request["properties"])
        self.assertNotIn("userAccount", request["properties"])
        response = self.client.post(path, {"asset": asset_id}, format="json")
        validator = self.assert_response(path, response, "post")
        self.assertEqual(response.json()["asset"]["uuid"], asset_id)
        self.assertFalse(validator.is_valid({**response.json(), "asset": asset_id}))
        self.assertFalse(Draft4Validator(request).is_valid({"asset": response.json()["asset"]}))

    def test_unset_profile_countries_are_nullable_outputs_without_admitting_null_input(self):
        UserProfile.objects.filter(pk=self.owner.profile.pk).update(citizenship_country=None, residence_country=None)
        path = "/api/user-profiles/{uuid}/"
        endpoint = f"/api/user-profiles/{self.owner.profile.pk}/"
        response = self.client.get(endpoint)
        validator = self.assert_response(path, response)
        request = self.request_schema(path, "patch")
        for name in ("citizenshipCountry", "residenceCountry"):
            with self.subTest(field=name):
                self.assertIsNone(response.json()[name])
                self.assertFalse(Draft4Validator(request["properties"][name]).is_valid(None))
                self.assertEqual(self.client.patch(endpoint, {name: None}, format="json").status_code, 400)
                wrong = deepcopy(response.json())
                wrong[name] = 7
                self.assertFalse(validator.is_valid(wrong))

    def test_device_registration_declares_its_real_inputs_and_both_success_codes(self):
        path = "/api/device-tokens/register/"
        payload = {"pushToken": "ExponentPushToken[new-generated-device]", "deviceType": "ios"}
        schema = self.request_schema(path)
        self.assertEqual(set(schema["properties"]), set(payload))
        self.assertTrue(Draft4Validator(schema).is_valid(payload))
        self.assertFalse(Draft4Validator(schema).is_valid({"pushToken": payload["pushToken"]}))
        for expected in (201, 200):
            response = self.client.post(path, payload, format="json")
            self.assertEqual(response.status_code, expected, response.content)
            self.assert_response(path, response, "post")
        unregister = "/api/device-tokens/unregister/"
        request = self.request_schema(unregister)
        self.assertEqual(set(request["properties"]), {"pushToken"})
        response = self.client.post(unregister, {"pushToken": payload["pushToken"]}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("content", self.document["paths"][unregister]["post"]["responses"]["204"])

    def test_swap_lookup_requires_exact_identity_and_only_initial_lookup_omits_digest(self):
        for suffix in ("swap", "swap/approval-status", "swap/approval-data"):
            path = f"/api/v1/trading/orders/{{uuid}}/{suffix}/"
            parameters = self.document["paths"][path]["get"]["parameters"]
            queries = {parameter["name"]: parameter for parameter in parameters if parameter["in"] == "query"}
            with self.subTest(path=path):
                self.assertEqual(
                    set(queries),
                    {"swap_uuid", "owner_account_uuid", "wallet_uuid", "settlement_digest"},
                )
                for name, parameter in queries.items():
                    self.assertEqual(parameter.get("required", False), name != "settlement_digest" or suffix != "swap")
                    if name.endswith("_uuid"):
                        self.assertEqual(parameter["schema"]["format"], "uuid")
