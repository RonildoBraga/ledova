import logging
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import serializers

from authentication.services.sessions import SessionService
from companies.models import LISTING_REQUIRED_DOCUMENTS, Company, CompanyDocument
from companies.services.company import submit_application
from integrations.expo_push import ExpoPushClient, ExpoPushError
from integrations.sumsub.client import SumSubService
from users.models import DeviceToken, UserProfile
from users.services.notifications import NotificationService
from users.services.setup import ensure_defaults
from users.tasks.notifications import send_push_notification

User = get_user_model()

EMAIL = "logging.privacy@example.test"
LOCAL_PART = "logging.privacy"
PASSWORD = "pw-12345678"
PUSH_TOKEN = "ExponentPushToken[private-device-identifier-0001]"


class LoggingPrivacyTestCase(TestCase):
    def capture(self):
        return self.assertLogs(logging.getLogger(), level=logging.DEBUG)

    def assert_private(self, captured):
        text = "\n".join(captured.output)
        self.assertNotIn(EMAIL, text)
        self.assertNotIn(LOCAL_PART, text)
        self.assertNotIn(PASSWORD, text)
        for start in range(0, len(PUSH_TOKEN) - 7):
            self.assertNotIn(PUSH_TOKEN[start : start + 8], text)
        return text


class AuthenticationLoggingTest(LoggingPrivacyTestCase):
    def make_user(self, *, signup_completed=True):
        user = User.objects.create_user(email=EMAIL, password=PASSWORD, is_active=True)
        UserProfile.objects.create(user=user, is_signup_completed=signup_completed)
        return user

    def test_a_successful_sign_in_logs_the_primary_key_and_no_email(self):
        user = self.make_user()

        with self.capture() as captured:
            SessionService.login(EMAIL, PASSWORD)

        text = self.assert_private(captured)
        self.assertIn(f"User {user.pk} successfully authenticated", text)

    def test_a_rejected_sign_in_logs_no_email(self):
        self.make_user()

        with self.capture() as captured:
            logging.getLogger(__name__).info("sign-in attempt rejected")
            with self.assertRaises(serializers.ValidationError):
                SessionService.login(EMAIL, "wrong-password-entirely")

        self.assert_private(captured)

    def test_a_sign_in_before_signup_completion_logs_no_email(self):
        self.make_user(signup_completed=False)

        with self.capture() as captured:
            logging.getLogger(__name__).info("sign-in attempt rejected")
            with self.assertRaises(serializers.ValidationError):
                SessionService.login(EMAIL, PASSWORD)

        self.assert_private(captured)

    def test_signup_logs_the_primary_key_of_the_account_it_created(self):
        with self.capture() as captured:
            user = SessionService.signup(EMAIL, PASSWORD, PASSWORD)

        text = self.assert_private(captured)
        self.assertIn(f"User account created/updated for user {user.pk}", text)
        self.assertIn("Created account", text)
        self.assertIn(f"Defaults ready for user {user.pk}", text)


class DefaultsLoggingTest(LoggingPrivacyTestCase):
    def test_ensure_defaults_names_the_rows_it_created_and_the_user_key(self):
        user = User.objects.create_user(email=EMAIL, password=PASSWORD, is_active=True)

        with self.capture() as captured:
            _, account, portfolio, _ = ensure_defaults(user)

        text = self.assert_private(captured)
        self.assertIn(f"Created account {account.uuid} for user {user.pk}", text)
        self.assertIn(f"Created portfolio {portfolio.uuid} for user {user.pk}", text)


class NotificationLoggingTest(LoggingPrivacyTestCase):
    def setUp(self):
        self.user = User.objects.create_user(email=EMAIL, password=PASSWORD, is_active=True)
        UserProfile.objects.create(user=self.user)
        with patch("users.services.notifications.ExpoPushClient"):
            self.service = NotificationService()

    def token(self):
        return DeviceToken.objects.create(user=self.user, push_token=PUSH_TOKEN, device_type=DeviceToken.DeviceType.IOS)

    def test_a_provider_failure_logs_the_user_key_and_the_reason(self):
        self.token()
        self.service.expo_client = Mock(send_batch=Mock(side_effect=ExpoPushError("upstream 502")))

        with self.capture() as captured:
            result = self.service.notify_user(self.user, "title", "body")

        self.assertEqual(result["status"], "error")
        text = self.assert_private(captured)
        self.assertIn(f"Failed to send to user {self.user.pk}: upstream 502", text)

    def test_deactivating_an_unregistered_device_logs_its_row_not_its_token(self):
        token = self.token()
        self.service.expo_client = Mock(
            send_batch=Mock(return_value=[{"status": "error", "details": {"error": "DeviceNotRegistered"}}])
        )

        with self.capture() as captured:
            self.service.notify_user(self.user, "title", "body")

        text = self.assert_private(captured)
        self.assertIn(f"Deactivated device token {token.pk} of user {self.user.pk}: DeviceNotRegistered", text)

    def test_a_user_with_no_device_logs_the_user_key(self):
        with self.capture() as captured:
            self.service.notify_user(self.user, "title", "body")

        text = self.assert_private(captured)
        self.assertIn(f"No active devices for user {self.user.pk}", text)

    def test_the_push_task_logs_the_user_id_it_was_given(self):
        self.token()

        with patch("users.tasks.notifications.NotificationService") as service_class:
            service_class.return_value.notify_user.return_value = {"status": "sent"}
            with self.capture() as captured:
                send_push_notification(user_id=str(self.user.pk), title="title", body="body")

        text = self.assert_private(captured)
        self.assertIn(f"Sent notification to user {self.user.pk}", text)


class CompanyLoggingTest(LoggingPrivacyTestCase):
    def test_submitting_an_application_logs_the_submitter_key(self):
        owner = User.objects.create_user(email=EMAIL, password=PASSWORD, is_active=True)
        company = Company.objects.create(owner=owner, name="Draft Pty Ltd", acn="123456789")
        for document_type in LISTING_REQUIRED_DOCUMENTS:
            CompanyDocument.objects.create(
                company=company,
                document_type=document_type,
                name=document_type.label,
                external_url="https://files.example.test/doc",
                file_size=10,
                mime_type="application/pdf",
            )

        with patch("companies.services.company.send_push_notification"):
            with self.capture() as captured:
                submit_application(company, owner)

        text = self.assert_private(captured)
        self.assertIn(f"Application submitted: {company.uuid} (Draft Pty Ltd) by user {owner.pk}", text)


APPLICANT_ID = "app_dossier_0001"

APPLICANT_DOSSIER = {
    "id": APPLICANT_ID,
    "externalUserId": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
    "email": EMAIL,
    "phone": "+61400111222",
    "review": {"reviewResult": {"reviewAnswer": "GREEN"}, "reviewStatus": "completed"},
    "info": {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "dob": "1815-12-10",
        "country": "AUS",
        "idDocs": [{"idDocType": "PASSPORT", "number": "PA1234567"}],
        "addresses": [{"street": "12 Byron Lane", "formattedAddress": "12 Byron Lane, Sydney NSW 2000"}],
    },
}

APPLICANT_STATUS = {
    "reviewId": "rev_0001",
    "reviewStatus": "completed",
    "reviewResult": {
        "reviewAnswer": "RED",
        "rejectLabels": ["FORGERY"],
        "moderationComment": "The passport PA1234567 of Ada Lovelace, born 1815-12-10, looks altered",
        "clientComment": f"{EMAIL} was rejected",
    },
}

DOSSIER_FRAGMENTS = ("Lovelace", "1815-12-10", "Byron Lane", "PA1234567", "+61400111222", "looks altered")


@override_settings(
    SUMSUB_API_KEY="api-key",
    SUMSUB_SECRET_KEY="secret-key",
    SUMSUB_BASE_URL="https://sumsub.example.test",
    SUMSUB_LEVEL_NAME="basic-kyc",
)
class IdentityProviderLoggingTest(LoggingPrivacyTestCase):
    def assert_no_dossier(self, captured):
        text = self.assert_private(captured)
        for fragment in DOSSIER_FRAGMENTS:
            self.assertNotIn(fragment, text)
        return text

    @patch("integrations.sumsub.client.requests.request")
    def test_fetching_applicant_data_logs_the_review_answer_not_the_dossier(self, request):
        request.return_value = MagicMock(ok=True, json=MagicMock(return_value=APPLICANT_DOSSIER))

        with self.capture() as captured:
            SumSubService().get_applicant_data(APPLICANT_ID)

        text = self.assert_no_dossier(captured)
        self.assertIn(f"Applicant data for {APPLICANT_ID}: review answer GREEN", text)

    @patch("integrations.sumsub.client.requests.request")
    def test_polling_applicant_status_logs_the_review_answer_not_the_moderation_comment(self, request):
        request.return_value = MagicMock(ok=True, json=MagicMock(return_value=APPLICANT_STATUS))

        with self.capture() as captured:
            SumSubService().get_applicant_status(APPLICANT_ID)

        text = self.assert_no_dossier(captured)
        self.assertIn(f"Status for {APPLICANT_ID}: review answer RED", text)

    @patch("integrations.sumsub.client.requests.request")
    def test_a_provider_error_logs_the_status_and_the_route_not_the_error_body(self, request):
        request.return_value = MagicMock(
            ok=False,
            status_code=403,
            text=f"forbidden for {EMAIL}",
            json=MagicMock(return_value={"description": f"forbidden for {EMAIL}"}),
            raise_for_status=Mock(side_effect=Exception("403")),
        )

        with self.capture() as captured:
            with self.assertRaises(Exception):
                SumSubService().get_applicant_status(APPLICANT_ID)

        text = self.assert_no_dossier(captured)
        self.assertIn(f"SumSub API Error: 403 for GET /resources/applicants/{APPLICANT_ID}/status", text)


class PushProviderLoggingTest(LoggingPrivacyTestCase):
    def push_client(self):
        client = ExpoPushClient()
        client.session = MagicMock()
        return client

    def test_an_unregistered_device_logs_the_expo_error_code_not_the_token(self):
        client = self.push_client()
        ticket = {
            "status": "error",
            "message": f'"{PUSH_TOKEN}" is not a registered push notification recipient device',
            "details": {"error": "DeviceNotRegistered", "expoPushToken": PUSH_TOKEN},
        }
        client.session.post.return_value = MagicMock(ok=True, json=MagicMock(return_value={"data": [ticket]}))

        with self.capture() as captured:
            client.send_batch([{"to": PUSH_TOKEN, "title": "title", "body": "body"}])

        text = self.assert_private(captured)
        self.assertIn("Notification 0 failed: DeviceNotRegistered", text)

    def test_a_rejected_batch_logs_the_status_and_the_size_not_the_provider_body(self):
        client = self.push_client()
        client.session.post.return_value = MagicMock(
            ok=False, status_code=400, text=f'{{"errors":[{{"message":""{PUSH_TOKEN}" is invalid"}}]}}'
        )

        with self.capture() as captured:
            with self.assertRaises(ExpoPushError):
                client.send_batch([{"to": PUSH_TOKEN, "title": "title", "body": "body"}])

        text = self.assert_private(captured)
        self.assertIn("API Error: 400 for 1 notification(s)", text)

    def test_a_malformed_token_is_reported_by_its_position_in_the_batch(self):
        with self.assertRaises(ExpoPushError) as raised:
            self.push_client().send_batch([{"to": PUSH_TOKEN[:-1], "title": "title", "body": "body"}])

        self.assertEqual(str(raised.exception), "Invalid Expo push token format in message 0")
