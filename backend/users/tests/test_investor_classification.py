from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, CompanyType
from users.exceptions import InvalidClassificationTransitionException
from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
)
from users.models.investor_classification import (
    ASSOCIATED_PERSON_SCOPE_ERROR,
    plus_years,
)
from users.services import transition_classification
from users.tests.factories import (
    make_classification,
    make_investor,
    rejected_classification,
    revoked_classification,
    verified_classification,
)

User = get_user_model()
ADMIN_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class InvestorClassificationTransitionTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="reviewer@example.test", password="pw-12345678", is_staff=True)
        _, self.account = make_investor("transitions")

    def test_verify_moves_a_submitted_claim_and_records_the_reviewer(self):
        classification = make_classification(self.account)
        expires_at = timezone.now() + timedelta(days=730)

        transition_classification(
            classification, "verify", reviewed_by=self.reviewer, expires_at=expires_at, notes="Checked the register"
        )

        classification.refresh_from_db()
        self.assertEqual(classification.status, InvestorClassificationStatus.VERIFIED)
        self.assertEqual(classification.reviewed_by, self.reviewer)
        self.assertEqual(classification.review_notes, "Checked the register")
        self.assertEqual(classification.expires_at, expires_at)
        self.assertIsNotNone(classification.reviewed_at)

    def test_verify_is_refused_once_the_claim_is_no_longer_submitted(self):
        classification = verified_classification(self.account, self.reviewer)

        with self.assertRaises(InvalidClassificationTransitionException) as caught:
            classification.verify(reviewed_by=self.reviewer, expires_at=timezone.now())

        self.assertIn("Cannot transition from 'Verified' to 'Verified'", str(caught.exception.detail))
        classification.refresh_from_db()
        self.assertEqual(classification.status, InvestorClassificationStatus.VERIFIED)

    def test_reject_moves_a_submitted_claim_and_records_the_reason(self):
        classification = make_classification(self.account)

        transition_classification(classification, "reject", reviewed_by=self.reviewer, reason="No certificate")

        classification.refresh_from_db()
        self.assertEqual(classification.status, InvestorClassificationStatus.REJECTED)
        self.assertEqual(classification.rejection_reason, "No certificate")

    def test_reject_is_refused_on_a_verified_claim(self):
        classification = verified_classification(self.account, self.reviewer)

        with self.assertRaises(InvalidClassificationTransitionException):
            classification.reject(reviewed_by=self.reviewer, reason="Too late")

        classification.refresh_from_db()
        self.assertEqual(classification.status, InvestorClassificationStatus.VERIFIED)

    def test_revoke_moves_a_verified_claim(self):
        classification = verified_classification(self.account, self.reviewer)

        transition_classification(classification, "revoke", reviewed_by=self.reviewer, reason="Certificate withdrawn")

        classification.refresh_from_db()
        self.assertEqual(classification.status, InvestorClassificationStatus.REVOKED)
        self.assertEqual(classification.rejection_reason, "Certificate withdrawn")
        self.assertFalse(classification.is_live)

    def test_revoke_is_refused_on_a_submitted_claim(self):
        classification = make_classification(self.account)

        with self.assertRaises(InvalidClassificationTransitionException):
            classification.revoke(reviewed_by=self.reviewer, reason="Not yet verified")

        classification.refresh_from_db()
        self.assertEqual(classification.status, InvestorClassificationStatus.SUBMITTED)


class InvestorClassificationExpiryTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="expiry@example.test", password="pw-12345678", is_staff=True)
        _, self.account = make_investor("expiry")

    def test_a_verified_claim_past_its_expiry_is_not_live_without_any_sweep(self):
        classification = verified_classification(
            self.account, self.reviewer, expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertEqual(classification.status, InvestorClassificationStatus.VERIFIED)
        self.assertFalse(classification.is_live)
        self.assertTrue(classification.is_expired)
        self.assertFalse(InvestorClassification.objects.live().exists())

    def test_a_verified_claim_inside_its_window_is_live(self):
        verified_classification(self.account, self.reviewer, expires_at=timezone.now() + timedelta(days=1))

        self.assertEqual(InvestorClassification.objects.live().count(), 1)

    def test_default_expiry_is_two_years_after_the_certificate_date(self):
        classification = make_classification(self.account, certificate_issued_at=date(2026, 3, 1))

        self.assertEqual(classification.default_expiry, plus_years(date(2026, 3, 1)))
        self.assertEqual(classification.default_expiry.year, 2028)

    def test_a_leap_day_certificate_expires_on_the_last_february_day(self):
        self.assertEqual(plus_years(date(2024, 2, 29)).date(), date(2026, 2, 28))


class InvestorClassificationOpenSubmissionConstraintTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="constraint@example.test", password="pw-1234567", is_staff=True)
        _, self.account = make_investor("constraint")

    def test_the_database_refuses_a_second_open_submission(self):
        make_classification(self.account)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_classification(self.account)

    def test_a_second_claim_is_allowed_once_the_first_is_verified(self):
        verified_classification(self.account, self.reviewer)

        make_classification(self.account)

        self.assertEqual(InvestorClassification.objects.filter(user_account=self.account).count(), 2)

    def test_a_second_claim_is_allowed_once_the_first_is_rejected(self):
        rejected_classification(self.account, self.reviewer)

        make_classification(self.account)

        self.assertEqual(InvestorClassification.objects.filter(user_account=self.account).count(), 2)

    def test_a_second_claim_is_allowed_once_the_first_is_revoked(self):
        revoked_classification(self.account, self.reviewer)

        make_classification(self.account)

        self.assertEqual(InvestorClassification.objects.filter(user_account=self.account).count(), 2)

    def test_the_constraint_is_a_partial_index_the_backend_actually_carries(self):
        constraints = connection.introspection.get_constraints(
            connection.cursor(), InvestorClassification._meta.db_table
        )
        self.assertIn("investor_classification_one_open_submission", constraints)


class AssociatedPersonScopeConstraintTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="scope@example.test", password="pw-12345678", is_staff=True)
        _, self.account = make_investor("scope")
        self.owner = User.objects.create_user(email="scope-owner@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Scope Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="123456789"
        )

    def test_the_database_refuses_an_associated_person_claim_that_names_no_issuer(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_classification(self.account, category=InvestorCategory.ASSOCIATED_PERSON)

    def test_the_database_refuses_an_issuer_on_any_other_category(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_classification(self.account, category=InvestorCategory.PROFESSIONAL_INVESTOR, company=self.company)

    def test_the_database_refuses_blanking_the_issuer_on_an_associated_person_claim(self):
        classification = make_classification(
            self.account, category=InvestorCategory.ASSOCIATED_PERSON, company=self.company
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvestorClassification.objects.filter(pk=classification.pk).update(company=None)

    def test_deleting_the_issuer_is_refused_while_an_associated_person_claim_names_it(self):
        classification = verified_classification(
            self.account, self.reviewer, category=InvestorCategory.ASSOCIATED_PERSON, company=self.company
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Company.objects.filter(pk=self.company.pk).delete()

        classification.refresh_from_db()
        self.assertEqual(classification.company, self.company)

    def test_an_associated_person_claim_that_names_its_issuer_is_accepted(self):
        classification = make_classification(
            self.account, category=InvestorCategory.ASSOCIATED_PERSON, company=self.company
        )

        self.assertEqual(classification.company, self.company)

    def test_the_constraint_is_one_the_backend_actually_carries(self):
        constraints = connection.introspection.get_constraints(
            connection.cursor(), InvestorClassification._meta.db_table
        )

        self.assertIn("investor_classification_associated_person_names_the_issuer", constraints)

    def test_the_admin_form_refuses_an_associated_person_claim_with_no_issuer(self):
        staff = User.objects.create_superuser(email="scope-staff@example.test", password="pw-12345678")
        self.client.force_login(staff)

        with override_settings(STORAGES=ADMIN_TEST_STORAGES):
            response = self.client.post(
                reverse("admin:users_investorclassification_add"),
                {
                    "user_account": str(self.account.pk),
                    "company": "",
                    "category": InvestorCategory.ASSOCIATED_PERSON,
                    "declared_basis": "A director of the issuer",
                    "declaration_accepted": "on",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ASSOCIATED_PERSON_SCOPE_ERROR)
        self.assertFalse(InvestorClassification.objects.exists())
