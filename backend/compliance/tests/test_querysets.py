"""The compliance managers were folded into their querysets; these pin the folded behaviour."""

from django.test import TestCase

from compliance.constants import (
    ACCOUNT_ACTION_NONE,
    ACCOUNT_ACTION_SUSPENDED,
    ACCOUNT_ACTION_TRANSACTION_HOLD,
    ALERT_SEVERITY_MEDIUM,
    ALERT_STATUS_CLOSED,
    ALERT_TYPE_LARGE_TRANSACTION,
    ALERT_TYPE_MANUAL,
)
from compliance.models import (
    AlertChecklistItem,
    AlertProcedureStep,
    AlertProcedureTemplate,
    ComplianceAlert,
)
from compliance.services import TierProgressionService
from users.models import UserAccount


def _alert(account, alert_type=ALERT_TYPE_MANUAL, **extra):
    return ComplianceAlert.objects.create(
        user_account=account,
        alert_type=alert_type,
        severity=ALERT_SEVERITY_MEDIUM,
        triggered_rule="TEST-001",
        description="test alert",
        **extra,
    )


def _template(alert_type, is_active=True):
    return AlertProcedureTemplate.objects.create(
        alert_type=alert_type,
        name=f"{alert_type} procedure",
        description="test",
        response_time_hours=24,
        is_active=is_active,
    )


class AlertProcedureTemplateQuerySetTest(TestCase):
    def test_for_alert_returns_the_active_template_for_the_alert_type(self):
        account = UserAccount.objects.create(account_number="ACC-TPL")
        active = _template(ALERT_TYPE_MANUAL)
        _template(ALERT_TYPE_LARGE_TRANSACTION, is_active=False)

        self.assertEqual(AlertProcedureTemplate.objects.for_alert(_alert(account)), active)
        self.assertIsNone(AlertProcedureTemplate.objects.for_alert(_alert(account, ALERT_TYPE_LARGE_TRANSACTION)))


class AlertChecklistItemQuerySetTest(TestCase):
    def test_pending_required_for_alert_is_scoped_ordered_and_skips_optional_or_done(self):
        account = UserAccount.objects.create(account_number="ACC-CHK")
        template = _template(ALERT_TYPE_MANUAL)
        second = AlertProcedureStep.objects.create(template=template, order=2, description="second")
        first = AlertProcedureStep.objects.create(template=template, order=1, description="first")
        done = AlertProcedureStep.objects.create(template=template, order=3, description="done")
        optional = AlertProcedureStep.objects.create(template=template, order=4, description="opt", is_required=False)

        alert, other = _alert(account), _alert(account)
        items = {
            step: AlertChecklistItem.objects.create(alert=alert, step=step) for step in (second, first, done, optional)
        }
        items[done].mark_completed(user=None)
        AlertChecklistItem.objects.create(alert=other, step=first)

        self.assertEqual(
            list(AlertChecklistItem.objects.pending_required_for_alert(alert)),
            [items[first], items[second]],
        )
        # as_manager() keeps the queryset methods on reverse related managers.
        self.assertEqual(alert.checklist_items.required_pending().count(), 2)


class ComplianceAlertQuerySetTest(TestCase):
    def setUp(self):
        self.account = UserAccount.objects.create(account_number="ACC-ALERT")
        self.other = UserAccount.objects.create(account_number="ACC-OTHER")

    def test_has_open_for_user_account_ignores_closed_and_foreign_alerts(self):
        _alert(self.other)
        _alert(self.account, status=ALERT_STATUS_CLOSED)
        self.assertFalse(ComplianceAlert.objects.has_open_for_user_account(self.account))
        self.assertFalse(TierProgressionService.has_open_compliance_alerts(self.account))

        _alert(self.account)
        self.assertTrue(ComplianceAlert.objects.has_open_for_user_account(self.account))
        self.assertTrue(TierProgressionService.has_open_compliance_alerts(self.account))

    def test_has_active_hold_for_user_account_matches_hold_and_suspension_only(self):
        _alert(self.account, account_action=ACCOUNT_ACTION_NONE)
        _alert(self.other, account_action=ACCOUNT_ACTION_SUSPENDED)
        self.assertFalse(ComplianceAlert.objects.has_active_hold_for_user_account(self.account))
        self.assertFalse(TierProgressionService.has_active_compliance_hold(self.account))

        _alert(self.account, account_action=ACCOUNT_ACTION_TRANSACTION_HOLD)
        self.assertTrue(ComplianceAlert.objects.has_active_hold_for_user_account(self.account))
        self.assertTrue(TierProgressionService.has_active_compliance_hold(self.account))
