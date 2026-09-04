"""The Alchemy webhook must reject every call when its signing key is unset."""

import hashlib
import hmac

from django.test import TestCase, override_settings


class AlchemyWebhookFailClosedTest(TestCase):
    url = "/webhooks/alchemy/"

    def _post(self, body, signature):
        return self.client.post(
            self.url, data=body, content_type="application/json", HTTP_X_ALCHEMY_SIGNATURE=signature
        )

    @override_settings(ALCHEMY_WEBHOOK_SIGNING_KEY="")
    def test_missing_signing_key_rejects(self):
        self.assertEqual(self._post(b"{}", "anything").status_code, 401)

    @override_settings(ALCHEMY_WEBHOOK_SIGNING_KEY="s3cret")
    def test_bad_signature_rejects(self):
        self.assertEqual(self._post(b"{}", "deadbeef").status_code, 401)

    @override_settings(ALCHEMY_WEBHOOK_SIGNING_KEY="s3cret")
    def test_valid_signature_passes_the_gate(self):
        body = b"{}"
        signature = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        self.assertNotEqual(self._post(body, signature).status_code, 401)
