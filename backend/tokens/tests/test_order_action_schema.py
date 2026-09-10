from uuid import uuid4

from drf_spectacular.generators import SchemaGenerator
from jsonschema import Draft4Validator
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from tokens.models import TransferOrder
from tokens.tests.order_action_fixtures import ActionFixtures


class OrderActionSchemaTest(ActionFixtures, APITransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = SchemaGenerator().get_schema(request=None, public=True)

    def resolve(self, schema):
        if "$ref" in schema:
            return self.resolve(
                {
                    **self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]],
                    **{key: value for key, value in schema.items() if key != "$ref"},
                }
            )
        if "allOf" in schema and len(schema["allOf"]) == 1:
            return {
                **self.resolve(schema["allOf"][0]),
                **{key: value for key, value in schema.items() if key != "allOf"},
            }
        return schema

    def response_schema(self, path, method="post", code="200"):
        return self.resolve(
            self.document["paths"][path][method]["responses"][code]["content"]["application/json"]["schema"]
        )

    def assert_keys(self, schema, body):
        schema = self.resolve(schema)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["properties"]), set(body))
        self.assertEqual(set(schema["required"]), set(body))
        return schema["properties"]

    def test_both_message_routes_declare_the_actual_snapshot_and_versioned_challenge(self):
        for purpose in ("cancel", "modify"):
            with self.subTest(purpose=purpose):
                body = self.identity() if purpose == "cancel" else self.modify_body()
                body["action_id"] = str(uuid4())
                response = self.message(purpose, body)
                self.assertEqual(response.status_code, 200, response.content)
                snapshot = response.json()
                fields = self.assert_keys(
                    self.response_schema(f"/api/v1/trading/orders/{{uuid}}/{purpose}/message/"), snapshot
                )
                challenge = snapshot["challenge"]
                self.assert_keys(fields["challenge"], challenge)
                self.assert_keys(self.resolve(fields["challenge"])["properties"]["domain"], challenge["domain"])
                self.assertEqual(challenge["purpose"], "order_" + purpose)
                self.assertEqual(challenge["message"]["actionId"], snapshot["actionId"])
                self.assertIsNone(snapshot["result"])
                self.assertIsNone(snapshot["refusal"])
                for nullable in ("challenge", "result", "refusal"):
                    self.assertTrue(self.resolve(fields[nullable])["nullable"])
                self.assert_keys(fields["review"], snapshot["review"])
                self.assert_keys(fields["intent"], snapshot["intent"])

    def test_context_and_modify_request_declarations_preserve_exact_decimal_strings(self):
        with use_operator():
            TransferOrder.objects.filter(pk=self.order.pk).update(
                quantity=9007199254740993, min_quantity=9007199254740992
            )
        response = self.context()
        self.assertEqual(response.status_code, 200, response.content)
        fields = self.assert_keys(
            self.response_schema("/api/v1/trading/orders/{uuid}/action-context/", "get"), response.json()
        )
        values = response.json()["currentValues"]
        current = self.assert_keys(fields["currentValues"], values)
        for name in ("quantity", "minQuantity", "pricePerShare", "filledQuantity", "remainingQuantity"):
            self.assertEqual(self.resolve(current[name])["type"], "string")
            self.assertIsInstance(values[name], str)
        request = self.document["paths"]["/api/v1/trading/orders/{uuid}/modify/message/"]["post"]["requestBody"][
            "content"
        ]["application/json"]["schema"]
        schema = self.resolve(request)
        self.assertEqual(
            set(schema["required"]),
            {"actionId", "ownerAccountUuid", "newQuantity", "newMinQuantity", "newPricePerShare"},
        )
        for name, value in (("newQuantity", values["quantity"]), ("newMinQuantity", values["minQuantity"])):
            validator = Draft4Validator(self.resolve(schema["properties"][name]))
            self.assertTrue(validator.is_valid(value))
            for invalid in (int(value), "01", "invalid", "9" * 20):
                self.assertFalse(validator.is_valid(invalid), (name, invalid))

    def test_applied_and_recorded_refusal_results_match_declared_discriminators(self):
        signed = self.signed()
        result = self.execute("cancel", signed)
        self.assertEqual(result.status_code, 200, result.content)
        schema = self.response_schema("/api/v1/trading/orders/{uuid}/cancel/")
        self.assert_keys(schema, result.json())
        applied = self.resolve(schema["properties"]["result"])
        variants = [self.resolve(item) for item in applied["oneOf"]]
        cancel = next(item for item in variants if "fromStatus" in item["properties"])
        self.assert_keys(cancel, result.json()["result"])
        self.assertEqual(self.resolve(cancel["properties"]["kind"])["enum"], ["cancel"])
        with use_operator():
            TransferOrder.objects.filter(pk=self.order.pk).update(status="open")
        self.action_id = uuid4()
        signed = self.signed()
        with use_operator():
            TransferOrder.objects.filter(pk=self.order.pk).update(status="matched")
        refused = self.execute("cancel", signed)
        self.assertEqual(refused.status_code, 400, refused.content)
        refusal_fields = self.assert_keys(schema["properties"]["refusal"], refused.json()["refusal"])
        self.assertIn(refused.json()["refusal"]["httpStatus"], self.resolve(refusal_fields["httpStatus"])["enum"])
        error_schema = self.response_schema("/api/v1/trading/orders/{uuid}/cancel/", code="400")
        self.assertIn({"$ref": "#/components/schemas/OrderActionSubmission"}, error_schema["anyOf"])
        lookup = self.response_schema("/api/v1/trading/orders/actions/{action_id}/", "get")
        self.assert_keys(lookup, self.recover().json())

    def test_retired_get_issuance_declares_its_refusal_without_a_success_envelope(self):
        operation = self.document["paths"]["/api/v1/trading/orders/{uuid}/cancel/message/"]["get"]
        self.assertNotIn("200", operation["responses"])
        self.assertIn("400", operation["responses"])
        response = self.client.get(f"/api/v1/trading/orders/{self.order.pk}/cancel/message/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "action_refresh_required")
        self.assertEqual(self.message().status_code, 200)
