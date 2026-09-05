from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from companies.models import Company, CompanyType
from operators.models import Operator
from users.constants import (
    ACCOUNT_STATUS_ACTIVE,
    ACCOUNT_STATUS_PENDING,
    ACCOUNT_STATUS_REJECTED,
    ACCOUNT_STATUS_SUSPENDED,
    ACCOUNT_STATUS_TERMINATED,
)
from users.exceptions import InvestorNotEligibleException
from users.models import (
    InvestorCategory,
    InvestorClassification,
    UserAccount,
    UserProfile,
)
from users.models.user_account import AccountRole
from users.services.eligibility import (
    ACCOUNT_NOT_IN_GOOD_STANDING,
    AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD,
    IDENTITY_NOT_VERIFIED,
    NO_INVESTOR_ACCOUNT,
    NO_LIVE_CLASSIFICATION,
    NOT_AN_INVESTOR_ACCOUNT,
    account_eligibility,
    investor_eligibility,
    require_investor_eligibility,
    require_subscription_eligibility,
)
from users.tests.factories import (
    make_classification,
    make_investor,
    rejected_classification,
    revoked_classification,
    verified_classification,
)

User = get_user_model()
FOUR_CATEGORIES = [
    InvestorCategory.PRODUCT_VALUE,
    InvestorCategory.ACCOUNTANT_CERTIFICATE,
    InvestorCategory.PROFESSIONAL_INVESTOR,
    InvestorCategory.ASSOCIATED_PERSON,
]


ASSOCIATED_PERSON_CONSTRAINT = "investor_classification_associated_person_names_the_issuer"


@contextmanager
def _scope_constraint_dropped():
    table = InvestorClassification._meta.db_table
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute("PRAGMA ignore_check_constraints = ON")
        else:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT {ASSOCIATED_PERSON_CONSTRAINT}")
    try:
        yield
    finally:
        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA ignore_check_constraints = OFF")


def _set_kyc_required(required):
    operator = Operator.get()
    operator.investor_kyc_required = required
    operator.save(update_fields=["investor_kyc_required"])


class InvestorEligibilityTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="eligibility@example.test", password="pw-12345678")
        self.user, self.account = make_investor("eligible")
        self.owner = User.objects.create_user(email="issuer@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Issuer Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="123456789"
        )
        self.other_company = Company.objects.create(
            owner=self.owner, name="Other Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="987654321"
        )
        _set_kyc_required(True)

    def test_the_four_categories_each_make_an_account_eligible(self):
        for category in FOUR_CATEGORIES:
            with self.subTest(category=category):
                _, account = make_investor(f"cat-{category}")
                company = self.company if category == InvestorCategory.ASSOCIATED_PERSON else None
                verified_classification(account, self.reviewer, category=category, company=company)
                user = account.user_profiles.first().user

                outcome = investor_eligibility(user, company=self.company)

                self.assertTrue(outcome.is_eligible, outcome.reasons)
                self.assertEqual(outcome.classification.category, category)
                self.assertEqual(outcome.account, account)

    def test_an_account_with_no_classification_is_refused(self):
        outcome = investor_eligibility(self.user)

        self.assertFalse(outcome.is_eligible)
        self.assertEqual(outcome.reasons, (NO_LIVE_CLASSIFICATION,))
        self.assertIsNone(outcome.classification)
        self.assertEqual(outcome.account, self.account)

    def test_a_submitted_classification_is_not_yet_live(self):
        make_classification(self.account)

        self.assertEqual(investor_eligibility(self.user).reasons, (NO_LIVE_CLASSIFICATION,))

    def test_an_expired_classification_is_refused(self):
        verified_classification(self.account, self.reviewer, expires_at=timezone.now() - timedelta(minutes=1))

        self.assertEqual(investor_eligibility(self.user).reasons, (NO_LIVE_CLASSIFICATION,))

    def test_a_revoked_classification_is_refused(self):
        revoked_classification(self.account, self.reviewer)

        self.assertEqual(investor_eligibility(self.user).reasons, (NO_LIVE_CLASSIFICATION,))

    def test_a_rejected_classification_is_refused(self):
        rejected_classification(self.account, self.reviewer)

        self.assertEqual(investor_eligibility(self.user).reasons, (NO_LIVE_CLASSIFICATION,))

    def test_a_company_scoped_claim_answers_for_that_company_only(self):
        verified_classification(
            self.account, self.reviewer, category=InvestorCategory.ASSOCIATED_PERSON, company=self.company
        )

        self.assertTrue(investor_eligibility(self.user, company=self.company).is_eligible)
        self.assertFalse(investor_eligibility(self.user, company=self.other_company).is_eligible)
        self.assertFalse(investor_eligibility(self.user).is_eligible)

    def test_an_associated_person_claim_without_an_issuer_answers_for_nobody(self):
        classification = verified_classification(
            self.account, self.reviewer, category=InvestorCategory.ASSOCIATED_PERSON, company=self.company
        )
        with _scope_constraint_dropped():
            InvestorClassification.objects.filter(pk=classification.pk).update(company=None)

            self.assertFalse(investor_eligibility(self.user, company=self.company).is_eligible)
            self.assertFalse(investor_eligibility(self.user, company=self.other_company).is_eligible)
            self.assertFalse(investor_eligibility(self.user).is_eligible)

    def test_an_unscoped_claim_answers_for_every_company(self):
        verified_classification(self.account, self.reviewer)

        self.assertTrue(investor_eligibility(self.user).is_eligible)
        self.assertTrue(investor_eligibility(self.user, company=self.company).is_eligible)
        self.assertTrue(investor_eligibility(self.user, company=self.other_company).is_eligible)

    def test_a_user_with_no_investor_account_is_refused(self):
        user = User.objects.create_user(email="issuer-only@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=user, full_name="Issuer only")
        _, account = make_investor("issuer-role", role=AccountRole.COMPANY)
        account.user_profiles.add(profile)

        outcome = investor_eligibility(user)

        self.assertEqual(outcome.reasons, (NO_INVESTOR_ACCOUNT,))
        self.assertIsNone(outcome.account)

    def test_an_anonymous_caller_has_no_account(self):
        self.assertEqual(investor_eligibility(None).reasons, (NO_INVESTOR_ACCOUNT,))

    def test_require_investor_eligibility_raises_403_with_the_reasons(self):
        with self.assertRaises(InvestorNotEligibleException) as caught:
            require_investor_eligibility(self.user)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.reasons, (NO_LIVE_CLASSIFICATION,))

    def test_require_investor_eligibility_returns_the_outcome_when_it_passes(self):
        verified_classification(self.account, self.reviewer)

        self.assertTrue(require_investor_eligibility(self.user).is_eligible)


class AccountStandingMatrixTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="standing@example.test", password="pw-12345678")

    def _standing(self, label, account_status, kyc_required, id_verified=True):
        _set_kyc_required(kyc_required)
        user, account = make_investor(label, account_status=account_status, id_verified=id_verified)
        verified_classification(account, self.reviewer)
        return investor_eligibility(user)

    def test_refused_statuses_are_refused_whether_or_not_kyc_is_required(self):
        for kyc_required in (True, False):
            for account_status in (ACCOUNT_STATUS_REJECTED, ACCOUNT_STATUS_SUSPENDED, ACCOUNT_STATUS_TERMINATED):
                with self.subTest(kyc_required=kyc_required, account_status=account_status):
                    outcome = self._standing(f"{account_status}-{kyc_required}", account_status, kyc_required)
                    self.assertFalse(outcome.is_eligible)
                    self.assertIn(ACCOUNT_NOT_IN_GOOD_STANDING, outcome.reasons)

    def test_active_passes_whether_or_not_kyc_is_required(self):
        for kyc_required in (True, False):
            with self.subTest(kyc_required=kyc_required):
                outcome = self._standing(f"active-{kyc_required}", ACCOUNT_STATUS_ACTIVE, kyc_required)
                self.assertTrue(outcome.is_eligible, outcome.reasons)

    def test_pending_is_refused_while_investor_kyc_is_required(self):
        outcome = self._standing("pending-on", ACCOUNT_STATUS_PENDING, True)

        self.assertFalse(outcome.is_eligible)
        self.assertIn(ACCOUNT_NOT_IN_GOOD_STANDING, outcome.reasons)

    def test_pending_passes_on_a_kyc_off_deployment(self):
        outcome = self._standing("pending-off", ACCOUNT_STATUS_PENDING, False, id_verified=False)

        self.assertTrue(outcome.is_eligible, outcome.reasons)

    def test_an_unverified_holder_is_refused_only_while_kyc_is_required(self):
        refused = self._standing("unverified-on", ACCOUNT_STATUS_ACTIVE, True, id_verified=False)
        allowed = self._standing("unverified-off", ACCOUNT_STATUS_ACTIVE, False, id_verified=False)

        self.assertIn(IDENTITY_NOT_VERIFIED, refused.reasons)
        self.assertTrue(allowed.is_eligible, allowed.reasons)

    def test_every_holder_on_a_joint_account_must_be_verified(self):
        _set_kyc_required(True)
        user, account = make_investor("joint", account_status=ACCOUNT_STATUS_ACTIVE)
        second = User.objects.create_user(email="second-holder@example.test", password="pw-12345678")
        account.user_profiles.add(UserProfile.objects.create(user=second, full_name="Second", is_id_verified=False))
        verified_classification(account, self.reviewer)

        self.assertIn(IDENTITY_NOT_VERIFIED, investor_eligibility(user).reasons)


class SubscriptionEligibilityTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="subscription@example.test", password="pw-12345678")
        self.owner = User.objects.create_user(email="sub-issuer@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Sub Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="111222333"
        )
        _set_kyc_required(True)

    def _account_for(self, label, category):
        _, account = make_investor(label)
        company = self.company if category == InvestorCategory.ASSOCIATED_PERSON else None
        verified_classification(account, self.reviewer, category=category, company=company)
        return account

    def test_product_value_is_refused_below_the_threshold(self):
        account = self._account_for("pv-below", InvestorCategory.PRODUCT_VALUE)

        with self.assertRaises(InvestorNotEligibleException) as caught:
            require_subscription_eligibility(account, self.company, Decimal("499999.99"))

        self.assertEqual(caught.exception.reasons, (AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD,))

    def test_product_value_passes_exactly_at_the_threshold(self):
        account = self._account_for("pv-at", InvestorCategory.PRODUCT_VALUE)

        outcome = require_subscription_eligibility(account, self.company, Decimal("500000.00"))

        self.assertTrue(outcome.is_eligible)

    def test_product_value_passes_above_the_threshold(self):
        account = self._account_for("pv-above", InvestorCategory.PRODUCT_VALUE)

        self.assertTrue(require_subscription_eligibility(account, self.company, Decimal("500000.01")).is_eligible)

    def test_the_threshold_does_not_apply_to_other_categories(self):
        for category in FOUR_CATEGORIES:
            if category == InvestorCategory.PRODUCT_VALUE:
                continue
            with self.subTest(category=category):
                account = self._account_for(f"other-{category}", category)
                outcome = require_subscription_eligibility(account, self.company, Decimal("1.00"))
                self.assertTrue(outcome.is_eligible)

    def test_an_ineligible_account_is_refused_before_the_amount_is_looked_at(self):
        _, account = make_investor("no-claim")

        with self.assertRaises(InvestorNotEligibleException) as caught:
            require_subscription_eligibility(account, self.company, Decimal("900000.00"))

        self.assertEqual(caught.exception.reasons, (NO_LIVE_CLASSIFICATION,))

    def test_the_outcome_names_the_account_that_was_asked_about(self):
        account = self._account_for("named-account", InvestorCategory.PROFESSIONAL_INVESTOR)

        outcome = require_subscription_eligibility(account, self.company, Decimal("1.00"))

        self.assertEqual(outcome.account, account)


class AccountScopedEligibilityTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="account-scope@example.test", password="pw-12345678")
        self.owner = User.objects.create_user(email="scope-issuer@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Scope Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="444555666"
        )
        _set_kyc_required(True)
        self.user, self.qualified = make_investor("two-accounts")
        self.profile = self.qualified.user_profiles.first()
        self.unqualified = UserAccount.objects.create(
            account_number="ACC-SECOND",
            account_status=ACCOUNT_STATUS_ACTIVE,
            role=AccountRole.INVESTOR,
            director=self.profile,
        )
        self.unqualified.user_profiles.add(self.profile)
        verified_classification(self.qualified, self.reviewer)

    def test_the_user_scoped_answer_is_true_because_one_account_qualifies(self):
        self.assertTrue(investor_eligibility(self.user).is_eligible)
        self.assertEqual(investor_eligibility(self.user).account, self.qualified)

    def test_the_unqualified_account_of_an_eligible_user_cannot_subscribe(self):
        with self.assertRaises(InvestorNotEligibleException) as caught:
            require_subscription_eligibility(self.unqualified, self.company, Decimal("900000.00"))

        self.assertEqual(caught.exception.reasons, (NO_LIVE_CLASSIFICATION,))

    def test_the_unqualified_account_of_an_eligible_user_is_refused_without_an_amount(self):
        outcome = account_eligibility(self.unqualified, self.company)

        self.assertFalse(outcome.is_eligible)
        self.assertEqual(outcome.reasons, (NO_LIVE_CLASSIFICATION,))

    def test_the_qualified_account_passes(self):
        self.assertTrue(account_eligibility(self.qualified, self.company).is_eligible)

    def test_a_non_investing_account_is_refused(self):
        _, company_account = make_investor("scope-company-role", role=AccountRole.COMPANY)

        outcome = account_eligibility(company_account)

        self.assertEqual(outcome.reasons, (NOT_AN_INVESTOR_ACCOUNT,))

    def test_no_account_is_refused(self):
        self.assertEqual(account_eligibility(None).reasons, (NOT_AN_INVESTOR_ACCOUNT,))


class MultipleLiveClaimsTest(TestCase):

    def setUp(self):
        self.reviewer = User.objects.create_user(email="multi-claim@example.test", password="pw-12345678")
        self.owner = User.objects.create_user(email="multi-issuer@example.test", password="pw-12345678")
        self.company = Company.objects.create(
            owner=self.owner, name="Multi Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="777888999"
        )
        _set_kyc_required(True)
        self.user, self.account = make_investor("multi")

    def _claim_created_at(self, category, created_at):
        claim = verified_classification(self.account, self.reviewer, category=category)
        InvestorClassification.objects.filter(pk=claim.pk).update(created_at=created_at)
        claim.refresh_from_db()
        return claim

    def test_a_small_amount_passes_on_the_professional_claim_whichever_was_submitted_last(self):
        now = timezone.now()
        for label, product_value_at, professional_at in (
            ("product value newest", now, now - timedelta(days=1)),
            ("professional newest", now - timedelta(days=1), now),
        ):
            with self.subTest(label):
                InvestorClassification.objects.all().delete()
                self._claim_created_at(InvestorCategory.PRODUCT_VALUE, product_value_at)
                professional = self._claim_created_at(InvestorCategory.PROFESSIONAL_INVESTOR, professional_at)

                outcome = require_subscription_eligibility(self.account, self.company, Decimal("1000.00"))

                self.assertEqual(outcome.classification, professional)

    def test_an_amount_at_the_threshold_may_be_answered_by_either_claim(self):
        now = timezone.now()
        self._claim_created_at(InvestorCategory.PRODUCT_VALUE, now)
        self._claim_created_at(InvestorCategory.PROFESSIONAL_INVESTOR, now - timedelta(days=1))

        outcome = require_subscription_eligibility(self.account, self.company, Decimal("500000.00"))

        self.assertTrue(outcome.is_eligible)
        self.assertEqual(outcome.classification.category, InvestorCategory.PRODUCT_VALUE)

    def test_with_no_amount_the_newest_live_claim_is_the_one_reported(self):
        now = timezone.now()
        self._claim_created_at(InvestorCategory.PRODUCT_VALUE, now - timedelta(days=1))
        newest = self._claim_created_at(InvestorCategory.ACCOUNTANT_CERTIFICATE, now)

        self.assertEqual(investor_eligibility(self.user).classification, newest)

    def test_a_product_value_only_account_is_still_refused_below_the_threshold(self):
        self._claim_created_at(InvestorCategory.PRODUCT_VALUE, timezone.now())

        with self.assertRaises(InvestorNotEligibleException) as caught:
            require_subscription_eligibility(self.account, self.company, Decimal("499999.99"))

        self.assertEqual(caught.exception.reasons, (AMOUNT_BELOW_PRODUCT_VALUE_THRESHOLD,))
