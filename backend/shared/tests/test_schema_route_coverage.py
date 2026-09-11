from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import include, path
from drf_spectacular.generators import SchemaGenerator
from rest_framework.response import Response
from rest_framework.views import APIView

from companies.serializers.document import CompanyDocumentSerializer
from shared.api.routes import (
    PROVIDER_EXCLUSIONS,
    registered_routes,
    schema_route_drift,
)


class SyntheticView(APIView):
    def get(self, request):
        return Response({})

    def delete(self, request):
        return Response(status=204)


class SyntheticRoutes:
    urlpatterns = [
        path("api/", include([path("synthetic/<uuid:uuid>/", SyntheticView.as_view())])),
        path("admin/synthetic/", SyntheticView.as_view()),
        path("health/", SyntheticView.as_view()),
    ]


class SchemaRouteComparisonTest(SimpleTestCase):
    def setUp(self):
        self.registered = {("get", "/api/things/{}/"), ("delete", "/api/things/{}/")}
        self.document = {
            "paths": {
                "/api/things/{uuid}/": {
                    "get": {"responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}}},
                    "delete": {"responses": {"204": {"description": "No content"}}},
                }
            }
        }

    def compare(self, document):
        return schema_route_drift(document, self.registered, set())

    def test_parameter_names_and_deliberate_bodyless_methods_do_not_change_route_identity(
        self,
    ):
        self.assertEqual(self.compare(self.document), [])
        with override_settings(ROOT_URLCONF=SyntheticRoutes):
            self.assertEqual(
                registered_routes(),
                {("get", "/api/synthetic/{}/"), ("delete", "/api/synthetic/{}/")},
            )

    def test_a_registered_operation_without_a_schema_fails(self):
        del self.document["paths"]["/api/things/{uuid}/"]["delete"]
        self.assertEqual(
            self.compare(self.document),
            ["DELETE /api/things/{}/: registered operation is absent from the schema"],
        )

    def test_a_wrong_verb_and_a_phantom_schema_route_both_fail(self):
        get = self.document["paths"]["/api/things/{uuid}/"].pop("get")
        self.document["paths"]["/api/things/{uuid}/"]["post"] = get
        findings = self.compare(self.document)
        self.assertIn(
            "GET /api/things/{}/: registered operation is absent from the schema",
            findings,
        )
        self.assertIn("POST /api/things/{}/: schema operation has no registered route", findings)

    def test_only_the_explicit_provider_exclusions_are_allowed_and_cannot_go_stale(
        self,
    ):
        registered = self.registered | PROVIDER_EXCLUSIONS
        self.assertEqual(schema_route_drift(self.document, registered), [])
        extra = ("post", "/webhooks/unclassified/")
        self.assertIn(
            "POST /webhooks/unclassified/: registered operation is absent from the schema",
            schema_route_drift(self.document, registered | {extra}),
        )
        removed = next(iter(PROVIDER_EXCLUSIONS))
        self.assertTrue(
            any(
                "exclusion outlives" in finding for finding in schema_route_drift(self.document, registered - {removed})
            )
        )
        self.document["paths"][removed[1]] = {removed[0]: {"responses": {"200": {"description": "Not for clients"}}}}
        self.assertTrue(
            any("deliberately excluded" in finding for finding in schema_route_drift(self.document, registered))
        )

    def test_an_error_only_compatibility_route_is_still_an_accounted_operation(self):
        self.document["paths"]["/api/things/{uuid}/"]["get"] = {
            "responses": {"400": {"content": {"application/json": {"schema": {"type": "object"}}}}}
        }
        self.assertEqual(self.compare(self.document), [])


class RegisteredSchemaCoverageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.document = SchemaGenerator().get_schema(request=None, public=True)

    def test_the_actual_schema_accounts_for_registered_routes_and_the_stream(self):
        self.assertEqual(schema_route_drift(self.document), [])
        self.assertIn("/api/v1/trading/events/stream/", self.document["paths"])

    def test_deleting_a_real_schema_route_is_detected_without_a_fixed_route_count(self):
        document = deepcopy(self.document)
        del document["paths"]["/api/v1/trading/wallets/balances/"]
        self.assertIn(
            "GET /api/v1/trading/wallets/balances/: registered operation is absent from the schema",
            schema_route_drift(document),
        )

    def test_response_linked_documents_keep_the_registered_file_route_and_external_link_variant(
        self,
    ):
        company_uuid, document_uuid = uuid4(), uuid4()
        document = SimpleNamespace(file=True, company=SimpleNamespace(uuid=company_uuid), uuid=document_uuid)
        serializer = CompanyDocumentSerializer()
        url = serializer.get_file_url(document)
        template = url.replace(str(company_uuid), "{company_uuid}").replace(str(document_uuid), "{uuid}")
        content = self.document["paths"][template]["get"]["responses"]["200"]["content"]
        self.assertEqual(content, {"*/*": {"schema": {"type": "string", "format": "binary"}}})
        document.file = None
        document.external_url = "https://documents.example.test/synthetic.pdf"
        self.assertEqual(serializer.get_file_url(document), document.external_url)
