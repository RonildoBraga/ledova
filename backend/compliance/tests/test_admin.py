from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from assets.models import Asset
from compliance.constants import (
    ALERT_SEVERITY_HIGH,
    ALERT_TYPE_LARGE_TRANSACTION,
    ALERT_TYPE_MANUAL,
    ASSESSMENT_STATUS_COMPLETE,
    PEP_TYPE_DOMESTIC,
    RISK_RATING_HIGH,
    RULE_TYPE_THRESHOLD,
    SCREENING_RESULT_REJECTED,
    SCREENING_STATUS_FAILED,
)
from compliance.models import (
    AlertChecklistItem,
    AlertProcedureStep,
    AlertProcedureTemplate,
    ComplianceAlert,
    CustomerRiskAssessment,
    MonitoringRule,
    TransactionScreening,
)
from users.models import UserAccount
from wallets.models import Transaction, Wallet

User = get_user_model()


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class ComplianceAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_superuser(email="officer@example.test", password="pw-12345678")
        cls.account = UserAccount.objects.create(account_number="ACC-ADMIN")
        wallet = Wallet.objects.create(
            user_account=cls.account, address="0x" + "a" * 40, chain="ethereum", verification_status="VERIFIED"
        )
        cls.tx = Transaction.objects.create(
            tx_hash="0xadmin",
            chain="ethereum",
            from_address=wallet.address,
            to_address="0x" + "b" * 40,
            asset=Asset.objects.create(symbol="ETH", name="Ether"),
            amount=Decimal("1"),
            wallet=wallet,
        )
        cls.rule = MonitoringRule.objects.create(
            rule_code="MON-001", name="Large", description="d", rule_type=RULE_TYPE_THRESHOLD, parameters={}
        )
        cls.alert = ComplianceAlert.objects.create(
            user_account=cls.account,
            transaction=cls.tx,
            monitoring_rule=cls.rule,
            alert_type=ALERT_TYPE_LARGE_TRANSACTION,
            severity=ALERT_SEVERITY_HIGH,
            triggered_rule="MON-001",
            description="big",
            smr_required=True,
        )
        cls.assessment = CustomerRiskAssessment.objects.create(
            user_account=cls.account,
            assessment_status=ASSESSMENT_STATUS_COMPLETE,
            overall_risk_rating=RISK_RATING_HIGH,
            customer_risk_score=3,
            geographic_risk_score=2,
            pep_type=PEP_TYPE_DOMESTIC,
        )
        cls.screening = TransactionScreening.objects.create(
            transaction=cls.tx,
            user_account=cls.account,
            provider_transaction_id=str(cls.tx.pk),
            to_address=cls.tx.to_address,
            status=SCREENING_STATUS_FAILED,
            result=SCREENING_RESULT_REJECTED,
            risk_level="HIGH",
            risk_signals=["sanctions <b>x</b>"],
            raw_response={"riskScore": 0.9},
            error_message="provider down",
        )
        cls.screening_alert = ComplianceAlert.objects.create(
            user_account=cls.account,
            alert_type=ALERT_TYPE_MANUAL,
            severity=ALERT_SEVERITY_HIGH,
            triggered_rule="CRYPTO-SCREEN",
            description="flagged",
            alert_data={"screening_id": str(cls.screening.pk)},
        )
        cls.template = AlertProcedureTemplate.objects.create(
            alert_type=ALERT_TYPE_LARGE_TRANSACTION, name="Large procedure", description="d", response_time_hours=36
        )
        cls.step = AlertProcedureStep.objects.create(
            template=cls.template, order=1, description="Review", condition="If SMR required"
        )
        cls.item = AlertChecklistItem.objects.create(alert=cls.alert, step=cls.step)
        cls.rows = (cls.rule, cls.alert, cls.assessment, cls.screening, cls.template, cls.step, cls.item)

    def setUp(self):
        self.client.force_login(self.officer)

    def run_action(self, model, action, obj):
        url = reverse(f"admin:compliance_{model}_changelist")
        return self.client.post(url, {"action": action, "_selected_action": [str(obj.pk)]}, follow=True)

    def test_every_changelist_and_change_page_renders(self):
        for obj in self.rows:
            model = obj._meta.model_name
            with self.subTest(model=model):
                changelist = self.client.get(reverse(f"admin:compliance_{model}_changelist"))
                self.assertEqual(changelist.status_code, 200)
                change = self.client.get(reverse(f"admin:compliance_{model}_change", args=[obj.pk]))
                self.assertEqual(change.status_code, 200)

    def test_screening_page_links_related_rows_and_escapes_provider_signals(self):
        response = self.client.get(reverse("admin:compliance_transactionscreening_change", args=[self.screening.pk]))
        self.assertContains(response, "sanctions &lt;b&gt;x&lt;/b&gt;")
        self.assertNotContains(response, "<b>x</b>")
        self.assertContains(response, reverse("admin:wallets_transaction_change", args=[self.tx.pk]))
        self.assertContains(response, reverse("admin:users_useraccount_change", args=[self.account.pk]))
        self.assertContains(
            response, reverse("admin:compliance_compliancealert_change", args=[self.screening_alert.pk])
        )
        changelist = self.client.get(reverse("admin:compliance_transactionscreening_changelist"))
        self.assertContains(changelist, "0xbbbbbbbb...bbbbbbbb")

    def test_alert_actions(self):
        self.run_action("compliancealert", "assign_to_me", self.alert)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.assigned_to, self.officer)
        self.assertIsNotNone(self.alert.assigned_at)

        self.run_action("compliancealert", "mark_as_reviewing", self.alert)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "reviewing")

        self.run_action("compliancealert", "close_alerts", self.alert)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "closed")
        self.assertEqual(self.alert.resolved_by, self.officer)

    def test_checklist_actions(self):
        skipped = AlertChecklistItem.objects.create(
            alert=self.alert, step=AlertProcedureStep.objects.create(template=self.template, order=2, description="x")
        )
        self.run_action("alertchecklistitem", "mark_completed", self.item)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_completed)
        self.assertEqual(self.item.completed_by, self.officer)

        self.run_action("alertchecklistitem", "mark_skipped", skipped)
        skipped.refresh_from_db()
        self.assertTrue(skipped.is_skipped)
        self.assertEqual(skipped.skip_reason, "Bulk skipped via admin")

    def test_retry_failed_screenings_action_reports_counts(self):
        service = MagicMock()
        service.retry_failed_screening.side_effect = lambda screening: screening
        with patch("compliance.admin.transaction_screening.CryptoScreeningService", return_value=service):
            response = self.run_action("transactionscreening", "retry_failed_screenings", self.screening)
        service.retry_failed_screening.assert_called_once_with(self.screening)
        self.assertContains(response, "Retried 1 screening(s): 0 succeeded, 1 still failed.")
