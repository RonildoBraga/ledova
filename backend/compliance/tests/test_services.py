from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from assets.models import Asset
from compliance.constants import (
    ALERT_STATUS_CLOSED,
    ALERT_TYPE_PERIODIC_REVIEW,
    ASSESSMENT_STATUS_COMPLETE,
    ASSESSMENT_STATUS_INCOMPLETE,
    ASSESSMENT_STATUS_PENDING,
    PEP_TYPE_DOMESTIC,
    PEP_TYPE_FOREIGN,
    RISK_RATING_EXTREME,
    RISK_RATING_HIGH,
    RISK_RATING_LOW,
    RISK_RATING_MEDIUM,
    RULE_TYPE_ADDRESS,
    RULE_TYPE_THRESHOLD,
)
from compliance.models import (
    ComplianceAlert,
    CustomerRiskAssessment,
    MonitoringRule,
    TransactionScreening,
)
from compliance.services.risk_assessment import RiskAssessmentService, overall_rating
from compliance.services.transaction_monitoring import (
    TransactionMonitoringService,
    check_rule,
    is_new_customer,
)
from compliance.tasks import check_periodic_reviews
from shared.models import Country
from users.models import FinancialProfile, UserAccount, UserProfile
from wallets.models import Transaction, Wallet

User = get_user_model()


class RuleDispatchTest(TestCase):
    def setUp(self):
        self.account = UserAccount.objects.create(account_number="ACC-RULE")
        wallet = Wallet.objects.create(
            user_account=self.account, address="0x" + "a" * 40, chain="ethereum", verification_status="VERIFIED"
        )
        self.tx = Transaction.objects.create(
            tx_hash="0xrule",
            chain="ethereum",
            from_address=wallet.address,
            to_address="0x" + "b" * 40,
            asset=Asset.objects.create(symbol="ETH", name="Ether"),
            amount=Decimal("1"),
            market_value=Decimal("12000"),
            wallet=wallet,
        )

    def test_threshold_rule_triggers_at_or_above_the_configured_amount(self):
        rule = MonitoringRule.objects.create(
            rule_code="MON-001",
            name="Large",
            description="d",
            rule_type=RULE_TYPE_THRESHOLD,
            parameters={"amount": 10000, "currency": "AUD"},
        )
        triggered, details = check_rule(rule, self.tx, self.account)
        self.assertTrue(triggered)
        self.assertEqual(details, {"amount": 12000.0, "threshold": 10000.0, "currency": "AUD"})

        rule.parameters = {"amount": 20000}
        self.assertEqual(check_rule(rule, self.tx, self.account), (False, {}))
        self.assertEqual(check_rule(rule, None, self.account), (False, {}))

    def test_unknown_rule_type_never_triggers(self):
        rule = MonitoringRule(rule_code="X-1", name="x", description="d", rule_type="not_a_rule")
        self.assertEqual(check_rule(rule, self.tx, self.account), (False, {}))

    def test_check_transaction_creates_an_alert_per_triggered_active_rule(self):
        rule = MonitoringRule.objects.create(
            rule_code="MON-001", name="Large", description="d", rule_type=RULE_TYPE_THRESHOLD, parameters={}
        )
        MonitoringRule.objects.create(
            rule_code="MON-099", name="Off", description="d", rule_type=RULE_TYPE_THRESHOLD, is_active=False
        )
        alerts = TransactionMonitoringService.check_transaction(self.tx, self.account)
        self.assertEqual([a.monitoring_rule for a in alerts], [rule])
        self.assertEqual(alerts[0].alert_type, "large_transaction")
        self.assertEqual(alerts[0].description, "Large: d")

    @override_settings(KYC_PROVIDER="", KYCAID_CRYPTO_MONITORING_ENABLED=False)
    def test_disabled_address_screening_needs_no_kyc_provider_and_lets_the_other_rules_run(self):
        address_rule = MonitoringRule.objects.create(
            rule_code="MON-004",
            name="High-Risk Wallet",
            description="d",
            rule_type=RULE_TYPE_ADDRESS,
            parameters={"check_type": "high_risk_wallet"},
        )
        threshold_rule = MonitoringRule.objects.create(
            rule_code="MON-001", name="Large", description="d", rule_type=RULE_TYPE_THRESHOLD, parameters={}
        )

        triggered, details = check_rule(address_rule, self.tx, self.account)
        self.assertTrue(triggered)
        self.assertEqual(details["error"], "Crypto monitoring is disabled")
        self.assertEqual(details["screening_trigger"], "large_transaction")
        self.assertEqual(TransactionScreening.objects.get(transaction=self.tx).provider, "disabled")

        alerts = TransactionMonitoringService.check_transaction(self.tx, self.account)
        self.assertEqual([alert.monitoring_rule for alert in alerts], [threshold_rule, address_rule])

    def test_is_new_customer_uses_the_activation_date(self):
        self.assertTrue(is_new_customer(self.account))
        self.account.activation_date = timezone.now() - timedelta(days=10)
        self.assertTrue(is_new_customer(self.account))
        self.assertFalse(is_new_customer(self.account, days=5))


class RiskAssessmentTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(email="risk@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(
            user=user, citizenship_country=Country.objects.create(code="au", name="Australia")
        )
        self.account = UserAccount.objects.create(account_number="ACC-RISK", director=self.profile)
        self.account.user_profiles.add(self.profile)

    def test_rating_thresholds(self):
        self.assertEqual(
            [overall_rating(s) for s in (3, 4, 5, 6, 7, 8, 9)],
            [RISK_RATING_LOW] * 2 + [RISK_RATING_MEDIUM] * 2 + [RISK_RATING_HIGH] * 2 + [RISK_RATING_EXTREME],
        )

    def test_completes_the_pending_assessment_in_place(self):
        pending = RiskAssessmentService.create_pending_assessment(self.account)
        self.assertEqual(pending.assessment_status, ASSESSMENT_STATUS_PENDING)

        assessment = RiskAssessmentService.calculate_and_create(self.account)

        self.assertEqual(assessment.pk, pending.pk)
        self.assertEqual(CustomerRiskAssessment.objects.count(), 1)
        self.assertEqual(assessment.assessment_status, ASSESSMENT_STATUS_COMPLETE)
        self.assertEqual((assessment.customer_risk_score, assessment.geographic_risk_score), (1, 1))
        self.assertEqual(assessment.overall_risk_rating, RISK_RATING_LOW)
        self.assertIn("Factors: domestic", assessment.assessment_reason)
        self.assertEqual(assessment.next_review_date, assessment.valid_until)

    def test_foreign_citizenship_domestic_pep_and_risky_occupation_raise_the_score(self):
        self.profile.citizenship_country = Country.objects.create(code="NZ", name="New Zealand")
        self.profile.id_document_type = "PASSPORT"
        self.profile.id_document_country = "NZ"
        self.profile.save()
        FinancialProfile.objects.create(
            user_profile=self.profile, occupation="Casino Gaming", source_of_funds=["other"]
        )

        assessment = RiskAssessmentService.calculate_and_create(
            self.account, pep_data={"pep_type": PEP_TYPE_DOMESTIC, "source": "test"}
        )

        self.assertEqual(CustomerRiskAssessment.objects.count(), 1)
        self.assertEqual((assessment.customer_risk_score, assessment.geographic_risk_score), (5, 2))
        self.assertEqual(assessment.overall_risk_rating, RISK_RATING_HIGH)
        self.assertEqual(assessment.pep_type, PEP_TYPE_DOMESTIC)
        self.assertEqual(assessment.pep_details, {"pep_type": PEP_TYPE_DOMESTIC, "source": "test"})
        self.assertTrue(assessment.high_risk_occupation)
        self.assertIn("foreign_country, foreign_passport", assessment.assessment_reason)

    def test_unknown_country_scores_two_and_foreign_pep_is_recorded(self):
        self.profile.citizenship_country = None
        self.profile.save()
        assessment = RiskAssessmentService.calculate_and_create(self.account, pep_data={"pep_type": PEP_TYPE_FOREIGN})
        self.assertEqual(assessment.geographic_risk_score, 2)
        self.assertEqual(assessment.pep_type, PEP_TYPE_FOREIGN)
        self.assertEqual(assessment.overall_risk_rating, RISK_RATING_LOW)

    def test_account_without_profile_gets_an_incomplete_assessment(self):
        orphan = UserAccount.objects.create(account_number="ACC-NOPROFILE")
        assessment = RiskAssessmentService.calculate_and_create(orphan)
        self.assertEqual(assessment.assessment_status, ASSESSMENT_STATUS_INCOMPLETE)
        self.assertEqual(assessment.assessment_reason, "Incomplete: No user profile available")


class PeriodicReviewTaskTest(TestCase):
    def test_raises_one_open_periodic_review_alert_per_overdue_assessment(self):
        account = UserAccount.objects.create(account_number="ACC-REVIEW")
        CustomerRiskAssessment.objects.create(
            user_account=account,
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            overall_risk_rating=RISK_RATING_MEDIUM,
            next_review_date=timezone.now() - timedelta(days=1),
        )
        CustomerRiskAssessment.objects.create(
            user_account=UserAccount.objects.create(account_number="ACC-FRESH"),
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            next_review_date=timezone.now() + timedelta(days=30),
        )

        self.assertEqual(check_periodic_reviews(timestamp=0), "Flagged 1 assessments for periodic review")
        self.assertEqual(check_periodic_reviews(timestamp=0), "Flagged 0 assessments for periodic review")

        alert = ComplianceAlert.objects.get()
        self.assertEqual(
            (alert.user_account, alert.alert_type, alert.triggered_rule),
            (account, ALERT_TYPE_PERIODIC_REVIEW, "REVIEW-001"),
        )
        self.assertEqual(alert.alert_data["current_rating"], RISK_RATING_MEDIUM)

        alert.status = ALERT_STATUS_CLOSED
        alert.save()
        self.assertEqual(check_periodic_reviews(timestamp=0), "Flagged 1 assessments for periodic review")
