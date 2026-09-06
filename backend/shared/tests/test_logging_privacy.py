import logging
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import serializers

from authentication.services.sessions import SessionService
from companies.models import LISTING_REQUIRED_DOCUMENTS, Company, CompanyDocument
from companies.services.company import submit_application
from integrations.expo_push import ExpoPushError
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
