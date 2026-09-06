import json
import logging
import re
from pathlib import Path

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

INTEGRATIONS = Path(__file__).resolve().parent.parent

HANDLERS = (
    INTEGRATIONS / "sumsub" / "webhook.py",
    INTEGRATIONS / "kycaid" / "webhook.py",
    INTEGRATIONS / "kycaid" / "crypto_webhook.py",
    INTEGRATIONS / "alchemy" / "webhook.py",
)

LOGGED_IDENTIFIERS = re.compile(
    r"logger\.\w+\(\s*f?\"[^\"]*\{[^}]*\b("
    r"applicant_id|applicantId|external_user_id|externalUserId|verification_id"
    r"|request_id|tx_hash|user\.id|user_profile|screening|signature|token|email"
    r"|len\(request\.body\)"
    r")\b"
)

APPLICANT_ID = "5f9a1c2e-0000-4000-8000-abcdefabcdef"


def _sources():
    return {path: path.read_text() for path in HANDLERS}


class WebhookLogSourceTest(TestCase):

    def test_no_handler_interpolates_an_identifier_into_a_log_line(self):
        offenders = []
        for path, source in _sources().items():
            for line_number, line in enumerate(source.splitlines(), 1):
                if LOGGED_IDENTIFIERS.search(line):
                    offenders.append(f"{path.name}:{line_number}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_no_handler_logs_a_request_body_length(self):
        offenders = [path.name for path, source in _sources().items() if "len(request.body)" in source]
        self.assertEqual(offenders, [])

    def test_no_handler_uses_a_log_prefix_constant(self):
        offenders = [path.name for path, source in _sources().items() if "[WEBHOOK" in source]
        self.assertEqual(offenders, [])

    def test_errors_are_logged_without_interpolating_the_exception(self):
        offenders = []
        for path, source in _sources().items():
            for line_number, line in enumerate(source.splitlines(), 1):
                if "logger.error" in line and ("{e}" in line or "{str(e)}" in line):
                    offenders.append(f"{path.name}:{line_number}")
        self.assertEqual(offenders, [])


@override_settings(SUMSUB_WEBHOOK_SECRET="", KYCAID_API_TOKEN="", ALCHEMY_WEBHOOK_SIGNING_KEY="")
class WebhookRejectionLogTest(TestCase):

    def setUp(self):
        self.client = APIClient()

    def _assert_rejection_leaks_nothing(self, url, payload):
        with self.assertLogs("integrations", level=logging.WARNING) as captured:
            response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertIn(response.status_code, (400, 401))
        emitted = "\n".join(captured.output)
        self.assertNotIn(APPLICANT_ID, emitted)
        self.assertNotIn("Body length", emitted)
        self.assertNotIn("[WEBHOOK", emitted)
        return emitted

    def test_sumsub_rejection_names_neither_the_applicant_nor_the_body(self):
        emitted = self._assert_rejection_leaks_nothing(
            "/webhooks/sumsub/", {"type": "applicantReviewed", "applicantId": APPLICANT_ID}
        )
        self.assertIn("invalid signature", emitted)

    def test_kycaid_rejection_names_neither_the_applicant_nor_the_body(self):
        emitted = self._assert_rejection_leaks_nothing(
            "/webhooks/kycaid/", {"type": "VERIFICATION_COMPLETED", "applicant_id": APPLICANT_ID}
        )
        self.assertIn("invalid signature", emitted)

    def test_alchemy_rejection_names_no_transaction(self):
        emitted = self._assert_rejection_leaks_nothing(
            "/webhooks/alchemy/", {"type": "ADDRESS_ACTIVITY", "event": {"activity": []}}
        )
        self.assertIn("Rejected webhook", emitted)
