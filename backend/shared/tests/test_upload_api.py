import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from redis.exceptions import ConnectionError
from rest_framework.test import APIClient, APITestCase

from authentication.services import TokenService
from companies.models import Company, CompanyDocument, CompanyType, DocumentType
from documents.models import Document
from shared.tests.upload_fixtures import pdf_bytes
from shared.upload_errors import UploadRejected, UploadUnavailable
from users.models import InvestorCategory, InvestorClassification
from users.tests.factories import make_investor


class UploadProtectionApiTest(APITestCase):
    def setUp(self):
        self.user, self.account = make_investor("upload-protection")
        self.company = Company.objects.create(
            owner=self.user, name="Synthetic Upload Ltd", company_type=CompanyType.PROPRIETARY, acn="123456789"
        )
        self.client.force_authenticate(self.user)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        storage_settings = override_settings(
            PRIVATE_MEDIA_ROOT=self.directory.name,
            FILE_UPLOAD_TEMP_DIR=self.directory.name,
            FILE_UPLOAD_MAX_MEMORY_SIZE=0,
        )
        storage_settings.enable()
        self.addCleanup(storage_settings.disable)
        self.quota = SimpleNamespace(
            take_rate_slot=Mock(return_value=(True, 0)), take_upload_bytes=Mock(return_value=(True, 0))
        )
        self.patch("shared.upload_limits.cache", self.quota)
        self.scan = self.patch("shared.uploads.scan_upload")
        self.defer = self.patch("documents.services.document.extract_document.defer")
        self.raw = pdf_bytes()
        self.routes = (
            ("/api/v1/documents/", "file", {"document_type": "payslip"}, 202),
            (
                f"/api/v1/companies/{self.company.uuid}/documents/",
                "file",
                {"document_type": DocumentType.ASIC_EXTRACT.value, "name": "Synthetic"},
                201,
            ),
            (
                "/api/investor-classifications/",
                "evidence_file",
                {
                    "user_account": str(self.account.uuid),
                    "category": InvestorCategory.PROFESSIONAL_INVESTOR,
                    "declaration_accepted": "true",
                    "declared_basis": "Synthetic evidence",
                },
                201,
            ),
        )

    def patch(self, target, *args, **kwargs):
        stub = patch(target, *args, **kwargs)
        value = stub.start()
        self.addCleanup(stub.stop)
        return value

    def post(self, route, raw=None, **extra):
        url, field, payload, _ = route
        file = SimpleUploadedFile("synthetic.pdf", self.raw if raw is None else raw, content_type="application/pdf")
        file.size = 1
        return self.client.post(url, {**payload, field: file, **extra}, format="multipart")

    def assert_no_evidence_or_extraction(self):
        for model in (Document, CompanyDocument, InvestorClassification):
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual(list(Path(self.directory.name).rglob("*")), [])
        self.defer.assert_not_called()

    def test_every_upload_route_charges_actual_bytes_before_scanning_and_preserves_the_original(self):
        def scan(raw):
            self.assertEqual(raw, self.raw)
            self.assertEqual(self.quota.take_rate_slot.call_count, 1)
            calls = self.quota.take_upload_bytes.call_args_list
            self.assertEqual(sum(call.args[1] for call in calls), len(raw))
            self.assertTrue(all(call.args[0] == f"upload-bytes:{self.user.pk}" for call in calls))

        self.scan.side_effect = scan
        for route in self.routes:
            with self.subTest(url=route[0]):
                self.quota.take_rate_slot.reset_mock()
                self.quota.take_upload_bytes.reset_mock()
                response = self.post(route)
                self.assertEqual(response.status_code, route[3], response.content)
        self.assertEqual(self.scan.call_count, 3)
        files = [path for path in Path(self.directory.name).rglob("*") if path.is_file()]
        self.assertEqual(len(files), 3)
        self.assertTrue(all(path.read_bytes() == self.raw for path in files))
        self.defer.assert_called_once()

    def test_spoofed_content_cannot_reach_storage_on_any_upload_route(self):
        for route in self.routes:
            with self.subTest(url=route[0]):
                response = self.post(route, b"<html>synthetic unsupported content</html>")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.scan.call_count, 3)
        self.assert_no_evidence_or_extraction()

    def test_a_malware_verdict_refuses_every_upload_route_before_storage(self):
        self.scan.side_effect = UploadRejected("The file failed the malware safety check.")
        for route in self.routes:
            with self.subTest(url=route[0]):
                response = self.post(route)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.scan.call_count, 3)
        self.assert_no_evidence_or_extraction()

    def test_scanner_unavailability_returns_503_and_persists_nothing_on_every_upload_route(self):
        self.scan.side_effect = UploadUnavailable()
        for route in self.routes:
            with self.subTest(url=route[0]):
                response = self.post(route)
                self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(self.scan.call_count, 3)
        self.assert_no_evidence_or_extraction()

    def test_cookie_csrf_parsing_still_accounts_for_all_bytes_before_scanning(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.cookies["access"] = TokenService.issue(self.user)[0]
        self.client.get("/api/auth/verify/")
        token = self.client.cookies["csrftoken"].value

        def scan(raw):
            calls = self.quota.take_upload_bytes.call_args_list
            self.assertEqual(sum(call.args[1] for call in calls), len(raw))
            self.assertEqual(self.quota.take_rate_slot.call_count, 1)

        self.scan.side_effect = scan
        response = self.post(self.routes[0], csrfmiddlewaretoken=token)

        self.assertEqual(response.status_code, 202, response.content)
        self.scan.assert_called_once_with(self.raw)

    def test_cookie_uploads_over_the_file_limit_stop_during_csrf_body_parsing(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.cookies["access"] = TokenService.issue(self.user)[0]
        self.client.get("/api/auth/verify/")
        token = self.client.cookies["csrftoken"].value

        with override_settings(UPLOAD_MAX_BYTES=len(self.raw) - 1):
            response = self.post(self.routes[0], csrfmiddlewaretoken=token)

        self.assertEqual(response.status_code, 400, response.content)
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    def test_the_request_quota_returns_429_before_reading_or_scanning_file_bytes(self):
        self.quota.take_rate_slot.return_value = (False, 7)
        for route in self.routes:
            with self.subTest(url=route[0]):
                response = self.post(route)
                self.assertEqual(response.status_code, 429, response.content)
                self.assertEqual(response["Retry-After"], "7")
        self.quota.take_upload_bytes.assert_not_called()
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    def test_the_byte_quota_returns_429_before_scanning_and_closes_temporary_uploads(self):
        self.quota.take_upload_bytes.return_value = (False, 9)
        for route in self.routes:
            with self.subTest(url=route[0]):
                response = self.post(route)
                self.assertEqual(response.status_code, 429, response.content)
                self.assertEqual(response["Retry-After"], "9")
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    def test_redis_errors_and_a_cache_without_atomic_operations_fail_closed(self):
        for quota in (
            SimpleNamespace(take_rate_slot=Mock(side_effect=ConnectionError("synthetic unavailable endpoint"))),
            SimpleNamespace(),
        ):
            with self.subTest(cache=quota), patch("shared.upload_limits.cache", quota):
                for route in self.routes:
                    response = self.post(route)
                    self.assertEqual(response.status_code, 503, response.content)
                    self.assertNotIn("endpoint", str(response.content))
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    def test_cache_failure_during_file_streaming_returns_503_and_closes_temporary_files(self):
        self.quota.take_upload_bytes.side_effect = ConnectionError("synthetic unavailable endpoint")
        for route in self.routes:
            response = self.post(route)
            self.assertEqual(response.status_code, 503, response.content)
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    def test_oversized_file_chunks_are_refused_before_the_scanner(self):
        with override_settings(UPLOAD_MAX_BYTES=len(self.raw) - 1):
            for route in self.routes:
                response = self.post(route)
                self.assertEqual(response.status_code, 400, response.content)
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    def test_extra_multipart_files_are_refused_and_all_temporary_files_are_closed(self):
        for route in self.routes:
            with self.subTest(url=route[0]):
                response = self.post(
                    route, extra_file=SimpleUploadedFile("second.pdf", self.raw, content_type="application/pdf")
                )
                self.assertEqual(response.status_code, 400, response.content)
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()

    @override_settings(UPLOAD_MAX_REQUEST_BYTES=1)
    def test_a_large_declared_body_is_refused_before_quota_or_scan_work(self):
        for route in self.routes:
            response = self.post(route)
            self.assertEqual(response.status_code, 413, response.content)
        self.quota.take_rate_slot.assert_not_called()
        self.scan.assert_not_called()
        self.assert_no_evidence_or_extraction()
