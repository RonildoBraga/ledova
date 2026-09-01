"""SumSub webhook must fail closed when the signing secret is unset.

Regression for the confirmed CRITICAL: an unset SUMSUB_WEBHOOK_SECRET
previously made signature verification return True, letting any
unauthenticated caller post a forged KYC status update.
"""

from django.test import TestCase, override_settings

from integrations.sumsub.client import SumSubService


class SumSubWebhookFailClosedTest(TestCase):
    @override_settings(SUMSUB_WEBHOOK_SECRET="")
    def test_missing_secret_rejects(self):
        service = SumSubService()
        self.assertFalse(service.verify_webhook_signature(b"{}", "anysig"))

    @override_settings(SUMSUB_WEBHOOK_SECRET=None)
    def test_none_secret_rejects(self):
        service = SumSubService()
        self.assertFalse(service.verify_webhook_signature(b"{}", "anysig"))

    @override_settings(SUMSUB_WEBHOOK_SECRET="s3cret")
    def test_bad_signature_rejects_when_secret_set(self):
        service = SumSubService()
        self.assertFalse(service.verify_webhook_signature(b'{"a":1}', "deadbeef"))
