from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import path
from drf_spectacular.drainage import GENERATOR_STATS, warn
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.settings import spectacular_settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from companies.models.company import CompanyStatus
from companies.models.document import DocumentType as CompanyDocumentType
from documents.models.document import DocumentType
from integrations.kyc.constants import VERIFICATION_STATUS_CHOICES
from offerings.models.offering import OfferingStatus
from offerings.models.subscription import SubscriptionStatus
from shared.api.routes import PROVIDER_EXCLUSIONS, registered_routes
from shared.constants import SUPPORTED_CHAINS
from tokens.models.choices import (
    RequestStatus,
    ShareTokenStatus,
    SwapOrderStatus,
    TransferOrderStatus,
    TransferOrderType,
)
from wallets.models.wallet import WalletSigningPreference


class SchemaDiagnosticsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        GENERATOR_STATS.reset()
        diagnostics = StringIO()
        with redirect_stderr(diagnostics):
            cls.document = SchemaGenerator().get_schema(request=None, public=True)
        cls.diagnostics = diagnostics.getvalue()

    def test_current_schema_generation_has_no_warnings_or_errors(self):
        self.assertEqual(self.diagnostics, "")

    def test_company_document_identity_has_uuid_format_on_detail_and_file_routes(self):
        prefix = "/api/v1/companies/{company_uuid}/documents/{uuid}/"
        for route, method in ((prefix, "get"), (prefix, "delete"), (prefix + "file/", "get")):
            with self.subTest(route=route, method=method):
                parameters = self.document["paths"][route][method]["parameters"]
                parameter = next(item for item in parameters if item["name"] == "uuid")
                self.assertEqual(parameter["schema"]["type"], "string")
                self.assertEqual(parameter["schema"].get("format"), "uuid")

    def test_domain_enum_names_preserve_the_existing_choice_values(self):
        choices = {
            "CompanyStatusEnum": CompanyStatus.values,
            "CapitalRequestStatusEnum": RequestStatus.values,
            "ShareTokenStatusEnum": ShareTokenStatus.values,
            "OfferingStatusEnum": OfferingStatus.values,
            "SubscriptionStatusEnum": SubscriptionStatus.values,
            "SwapOrderStatusEnum": SwapOrderStatus.values,
            "TransferOrderStatusEnum": TransferOrderStatus.values,
            "TransferOrderTypeEnum": TransferOrderType.values,
            "UserDocumentTypeEnum": DocumentType.values,
            "CompanyDocumentDocumentTypeEnum": CompanyDocumentType.values,
            "SupportedWalletChainEnum": sorted(SUPPORTED_CHAINS),
            "UserVerificationStatusEnum": [value for value, _ in VERIFICATION_STATUS_CHOICES],
            "WalletSigningPreferenceEnum": [value for value, _ in WalletSigningPreference.choices()],
        }
        schemas = self.document["components"]["schemas"]
        for name, values in choices.items():
            with self.subTest(name=name):
                self.assertIn(name, schemas)
                self.assertEqual(schemas[name]["enum"], values)
        self.assertNotEqual(choices["CompanyDocumentDocumentTypeEnum"], choices["UserDocumentTypeEnum"])
        self.assertEqual(
            schemas["OrderActionCancelResult"]["properties"]["fromStatus"]["$ref"],
            "#/components/schemas/TransferOrderStatusEnum",
        )
        for field in ("signingPreference", "walletType"):
            self.assertIn(
                {"$ref": "#/components/schemas/WalletSigningPreferenceEnum"},
                schemas["Wallet"]["properties"][field]["oneOf"],
            )


class FirstDiagnosticStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["cold", "warm"])


class FirstDiagnosticStatusCopySerializer(FirstDiagnosticStatusSerializer):
    pass


class SecondDiagnosticStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["open", "closed"])


class SecondDiagnosticStatusCopySerializer(SecondDiagnosticStatusSerializer):
    pass


class CollidingDiagnosticSerializer(serializers.Serializer):
    first = FirstDiagnosticStatusSerializer()
    first_copy = FirstDiagnosticStatusCopySerializer()
    second = SecondDiagnosticStatusSerializer()
    second_copy = SecondDiagnosticStatusCopySerializer()


class CleanDiagnosticView(APIView):
    @extend_schema(responses=FirstDiagnosticStatusSerializer)
    def get(self, request):
        return Response({"status": "cold"})


class CollidingDiagnosticView(APIView):
    @extend_schema(responses=CollidingDiagnosticSerializer)
    def get(self, request):
        return Response({})


class UndeclaredDiagnosticView(APIView):
    def get(self, request):
        return Response({})


class SchemaExportDiagnosticsTest(SimpleTestCase):
    def export(self, view, stale_warning=False):
        class Routes:
            urlpatterns = [path("api/synthetic/", view.as_view())]

        command = "shared.management.commands.export_api_schema."
        hooks = [
            hook
            for hook in spectacular_settings.POSTPROCESSING_HOOKS
            if hook.__name__ != "document_trading_events_stream"
        ]
        with (
            TemporaryDirectory() as directory,
            override_settings(ROOT_URLCONF=Routes),
            patch.object(spectacular_settings, "POSTPROCESSING_HOOKS", hooks),
        ):
            destination = Path(directory) / "schema.json"
            GENERATOR_STATS.reset()
            diagnostics = StringIO()
            with (
                patch(command + "measured_environment", return_value={}),
                patch(command + "environment_drift", return_value=[]),
                patch(command + "MigrationExecutor") as executor,
                patch(command + "registered_routes", return_value=registered_routes() | PROVIDER_EXCLUSIONS),
                redirect_stderr(diagnostics),
            ):
                executor.return_value.migration_plan.return_value = []
                if stale_warning:
                    warn("Synthetic warning from a preceding generation")
                error = None
                try:
                    call_command(
                        "export_api_schema",
                        file=destination,
                        report=Path(directory) / "environment.json",
                        stdout=StringIO(),
                    )
                except CommandError as caught:
                    error = str(caught)
                return error, destination.exists(), diagnostics.getvalue()

    def test_export_refuses_enum_collision_warnings_before_writing_a_schema(self):
        error, written, diagnostics = self.export(CollidingDiagnosticView)
        self.assertIn("enum naming", diagnostics)
        self.assertIsNotNone(error)
        self.assertFalse(written)

    def test_export_refuses_unresolved_response_errors_before_writing_a_schema(self):
        error, written, diagnostics = self.export(UndeclaredDiagnosticView)
        self.assertIn("unable to guess serializer", diagnostics)
        self.assertIsNotNone(error)
        self.assertFalse(written)

    def test_clean_generation_succeeds_even_after_an_unrelated_generation_warning(self):
        error, written, diagnostics = self.export(CleanDiagnosticView, stale_warning=True)
        self.assertIn("Synthetic warning from a preceding generation", diagnostics)
        self.assertIsNone(error)
        self.assertTrue(written)
