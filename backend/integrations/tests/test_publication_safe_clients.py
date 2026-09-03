from unittest.mock import MagicMock, patch

import requests
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from integrations.kycaid.client import KYCAIDService
from integrations.sendgrid_email.client import SendGridClient
from integrations.transak.client import TransakClient
from integrations.transak.exceptions import TransakApiError, TransakConfigurationError


class TransakClientBoundaryTests(SimpleTestCase):
    @override_settings(
        TRANSAK_API_KEY="key",
        TRANSAK_API_SECRET="secret",
        TRANSAK_API_URL="",
        TRANSAK_API_GATEWAY_URL="",
    )
    def test_explicit_service_urls_are_required(self) -> None:
        with self.assertRaises(TransakConfigurationError):
            TransakClient()

    @override_settings(
        TRANSAK_API_KEY="key",
        TRANSAK_API_SECRET="secret",
        TRANSAK_API_URL="https://api.example.test/",
        TRANSAK_API_GATEWAY_URL="https://gateway.example.test/",
        TRANSAK_REFERRER_DOMAIN="example.test",
    )
    def test_explicit_https_configuration_is_preserved(self) -> None:
        client = TransakClient()

        self.assertEqual(client.api_url, "https://api.example.test")
        self.assertEqual(client.api_gateway_url, "https://gateway.example.test")
        self.assertEqual(client.referrer_domain, "example.test")

    @override_settings(
        TRANSAK_API_KEY="key",
        TRANSAK_API_SECRET="secret",
        TRANSAK_API_URL="https://api.example.test",
        TRANSAK_API_GATEWAY_URL="https://gateway.example.test",
    )
    @patch("integrations.transak.client.requests.post")
    def test_provider_error_body_is_not_exposed(self, post: MagicMock) -> None:
        post.return_value = MagicMock(status_code=400, text="private provider output")

        with self.assertRaises(TransakApiError) as raised:
            TransakClient()._refresh_access_token()

        self.assertNotIn("private provider output", str(raised.exception))


class KYCAIDClientBoundaryTests(SimpleTestCase):
    @override_settings(KYCAID_API_TOKEN="", KYCAID_BASE_URL="")
    def test_missing_token_fails_webhook_verification_closed(self) -> None:
        service = KYCAIDService()

        self.assertFalse(service.verify_webhook_signature(b"payload", "signature"))

    @override_settings(KYCAID_API_TOKEN="", KYCAID_BASE_URL="")
    @patch("integrations.kycaid.client.requests.request")
    def test_unconfigured_provider_is_not_called(self, request: MagicMock) -> None:
        with self.assertRaises(ImproperlyConfigured):
            KYCAIDService().get_applicant_status("private-applicant-id")

        request.assert_not_called()

    @override_settings(
        KYCAID_API_TOKEN="token",
        KYCAID_BASE_URL="https://kyc.example.test",
    )
    @patch("integrations.kycaid.client.requests.request")
    def test_provider_error_body_is_not_logged_or_raised(self, request: MagicMock) -> None:
        request.return_value = MagicMock(ok=False, status_code=400, text="private provider output")

        with self.assertRaises(requests.HTTPError) as raised:
            KYCAIDService().get_applicant_status("private-applicant-id")

        self.assertNotIn("private provider output", str(raised.exception))

    @override_settings(PUBLIC_API_BASE_URL="http://localhost:8000/")
    def test_callback_defaults_to_configured_local_public_api(self) -> None:
        self.assertEqual(
            KYCAIDService._get_crypto_callback_url(),
            "http://localhost:8000/webhooks/kycaid/crypto/",
        )


class SendGridClientBoundaryTests(SimpleTestCase):
    @override_settings(SENDGRID_API_KEY="", SENDGRID_API_URL="", DEFAULT_FROM_EMAIL="noreply@example.test")
    @patch("integrations.sendgrid_email.client.requests.post")
    def test_without_a_key_mail_goes_through_the_django_backend(self, post: MagicMock) -> None:
        result = SendGridClient().send_email("person@example.test", "Subject", "<p>Your code is 123456</p>")

        self.assertTrue(result["success"])
        post.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["person@example.test"])
        self.assertEqual(message.from_email, "noreply@example.test")
        self.assertEqual(message.subject, "Subject")
        self.assertEqual(message.body, "Your code is 123456")
        self.assertEqual(message.alternatives[0][0], "<p>Your code is 123456</p>")

    @override_settings(
        SENDGRID_API_KEY="key",
        SENDGRID_API_URL="",
        DEFAULT_FROM_EMAIL="noreply@localhost",
    )
    @patch("integrations.sendgrid_email.client.requests.post")
    def test_explicit_service_url_is_required(self, post: MagicMock) -> None:
        result = SendGridClient().send_email("person@example.test", "Subject", "Private body")

        self.assertFalse(result["success"])
        post.assert_not_called()

    @override_settings(
        SENDGRID_API_KEY="key",
        SENDGRID_API_URL="https://sendgrid.example.test/v3/mail/send",
        DEFAULT_FROM_EMAIL="noreply@example.test",
    )
    @patch("integrations.sendgrid_email.client.requests.post")
    def test_provider_error_body_and_recipient_are_not_returned(self, post: MagicMock) -> None:
        post.return_value = MagicMock(status_code=400, text="private provider output")

        result = SendGridClient().send_email("private@example.test", "Subject", "Private body")

        self.assertFalse(result["success"])
        self.assertNotIn("private provider output", result["error"])
        self.assertNotIn("private@example.test", result["error"])
