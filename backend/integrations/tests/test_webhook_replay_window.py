import hashlib
import hmac
import json
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.webhooks import WEBHOOK_MAX_AGE_SECONDS, is_stale, signed_timestamp

SECRET = "s3cret"


def _sumsub_ts(moment):
    return moment.astimezone(dt_timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class WebhookFreshnessTest(TestCase):

    def test_a_recent_timestamp_is_fresh(self):
        self.assertFalse(is_stale({"createdAtMs": _sumsub_ts(timezone.now())}))

    def test_an_old_timestamp_is_stale(self):
        old = timezone.now() - timedelta(seconds=WEBHOOK_MAX_AGE_SECONDS + 60)
        self.assertTrue(is_stale({"createdAtMs": _sumsub_ts(old)}))

    def test_a_far_future_timestamp_is_stale(self):
        ahead = timezone.now() + timedelta(seconds=WEBHOOK_MAX_AGE_SECONDS + 60)
        self.assertTrue(is_stale({"createdAtMs": _sumsub_ts(ahead)}))

    def test_a_payload_with_no_timestamp_is_not_stale(self):
        self.assertFalse(is_stale({"type": "VERIFICATION_COMPLETED", "applicant_id": "a"}))

    def test_an_unparseable_timestamp_is_not_stale(self):
        self.assertFalse(is_stale({"createdAt": "not a date"}))

    def test_iso_8601_with_a_zulu_suffix_parses(self):
        moment = timezone.now().replace(microsecond=0)
        value = moment.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertIsNotNone(signed_timestamp({"createdAt": value}))
        self.assertFalse(is_stale({"createdAt": value}))

    def test_epoch_seconds_and_milliseconds_both_parse(self):
        now = timezone.now()
        self.assertFalse(is_stale({"timestamp": int(now.timestamp())}))
        self.assertFalse(is_stale({"timestamp": int(now.timestamp() * 1000)}))


@override_settings(SUMSUB_WEBHOOK_SECRET=SECRET)
class SumSubReplayWindowTest(TestCase):

    def setUp(self):
        self.client = APIClient()

    def _post(self, payload):
        body = json.dumps(payload).encode()
        signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            "/webhooks/sumsub/",
            data=body,
            content_type="application/json",
            HTTP_X_PAYLOAD_DIGEST=signature,
        )

    def test_a_correctly_signed_but_stale_webhook_is_refused(self):
        old = timezone.now() - timedelta(seconds=WEBHOOK_MAX_AGE_SECONDS + 60)
        response = self._post({"type": "applicantReviewed", "applicantId": "a", "createdAtMs": _sumsub_ts(old)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Stale webhook")

    def test_a_correctly_signed_fresh_webhook_passes_the_window(self):
        response = self._post(
            {"type": "applicantReviewed", "applicantId": "a", "createdAtMs": _sumsub_ts(timezone.now())}
        )
        self.assertNotEqual(response.json().get("error"), "Stale webhook")
