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
