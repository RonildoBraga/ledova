from django.contrib.auth import get_user_model
from django.test import TestCase

from companies.models import Company, CompanyStatus
from companies.serializers import ApplicationStatusSerializer, CompanyDetailSerializer

User = get_user_model()

COMPANY_DETAIL_KEYS = {
    "uuid",
    "name",
    "trading_name",
    "display_name",
    "company_type",
    "company_type_display",
    "acn",
    "abn",
    "status",
    "status_display",
    "email",
    "phone",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postcode",
    "country",
    "operator_wallet",
    "submitted_at",
    "review_started_at",
    "approved_at",
    "activated_at",
    "info_requested_at",
    "info_request_reason",
    "additional_info_response",
    "rejection_at",
    "rejection_reason",
    "withdrawn_at",
    "withdrawal_reason",
    "description",
    "industry",
    "founded_year",
    "is_active",
    "is_approved",
    "is_pending_review",
    "can_issue_tokens",
    "primary_contact",
    "documents",
    "created_at",
    "updated_at",
}

APPLICATION_STATUS_KEYS = {
    "uuid",
    "name",
    "status",
    "status_display",
    "submitted_at",
    "review_started_at",
    "review_completed_at",
    "info_requested_at",
    "info_request_reason",
    "approved_at",
    "activated_at",
    "rejection_reason",
    "rejection_at",
    "withdrawn_at",
    "withdrawal_reason",
    "is_pending_review",
    "is_approved",
    "is_active",
}


class SerializerContractTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="contract@example.test", password="pw-12345678")
        self.company = Company.objects.create(owner=self.owner, name="Contract Pty Ltd", acn="123456789")

    def test_company_detail_serializer_key_set(self):
        self.assertEqual(set(CompanyDetailSerializer(self.company).data.keys()), COMPANY_DETAIL_KEYS)

    def test_application_status_serializer_key_set(self):
        self.assertEqual(set(ApplicationStatusSerializer(self.company).data.keys()), APPLICATION_STATUS_KEYS)

    def test_company_detail_serializer_exposes_rejection_outcome(self):
        self.company.status = CompanyStatus.SUBMITTED
        self.company.save(update_fields=["status"])
        self.company.reject("Insufficient documentation.", rejected_by=self.owner)

        data = CompanyDetailSerializer(self.company).data

        self.assertEqual(data["rejection_reason"], "Insufficient documentation.")
        self.assertIsNotNone(data["rejection_at"])

    def test_application_status_serializer_exposes_withdrawal_outcome(self):
        self.company.withdraw("Changed our minds.")

        data = ApplicationStatusSerializer(self.company).data

        self.assertEqual(data["withdrawal_reason"], "Changed our minds.")
        self.assertIsNotNone(data["withdrawn_at"])

    def test_company_detail_serializer_exposes_withdrawal_outcome(self):
        self.company.withdraw("No longer proceeding.")

        data = CompanyDetailSerializer(self.company).data

        self.assertEqual(data["withdrawal_reason"], "No longer proceeding.")
        self.assertIsNotNone(data["withdrawn_at"])

    def test_all_added_fields_are_read_only(self):
        writable = {name for name, field in CompanyDetailSerializer().fields.items() if not field.read_only}
        self.assertFalse(writable & {"rejection_at", "rejection_reason", "withdrawn_at", "withdrawal_reason"})
