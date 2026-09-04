"""The seed commands load the data modules idempotently and reconcile the tables to them."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from compliance.constants import ALERT_TYPE_MANUAL, RULE_TYPE_THRESHOLD
from compliance.models import AlertProcedureStep, AlertProcedureTemplate, MonitoringRule
from compliance.seeds.monitoring_rules import MONITORING_RULES
from compliance.seeds.procedure_templates import PROCEDURE_TEMPLATES


def run(command):
    out = StringIO()
    call_command(command, stdout=out)
    return out.getvalue()


class SyncMonitoringRulesTest(TestCase):
    def test_loads_every_rule_once_and_removes_unknown_codes(self):
        MonitoringRule.objects.create(rule_code="OLD-999", name="Old", description="d", rule_type=RULE_TYPE_THRESHOLD)

        self.assertIn("11 created, 0 updated, 1 deleted", run("sync_monitoring_rules"))
        self.assertEqual(MonitoringRule.objects.count(), len(MONITORING_RULES))
        self.assertFalse(MonitoringRule.objects.filter(rule_code="OLD-999").exists())
        first = MonitoringRule.objects.get(rule_code="MON-001")
        self.assertEqual(first.parameters, {"amount": 10000, "currency": "AUD"})
        self.assertEqual(first.alert_severity, "medium")

        rows = list(MonitoringRule.objects.order_by("rule_code").values("rule_code", "name", "parameters", "is_active"))
        first.name = "edited by hand"
        first.save()

        self.assertIn("0 created, 11 updated, 0 deleted", run("sync_monitoring_rules"))
        self.assertEqual(
            list(MonitoringRule.objects.order_by("rule_code").values("rule_code", "name", "parameters", "is_active")),
            rows,
        )
        # The data module must survive the loader untouched so a second process sees the same rows.
        self.assertEqual(MONITORING_RULES[0]["rule_code"], "MON-001")


class SyncProcedureTemplatesTest(TestCase):
    def test_loads_every_template_and_step_once_and_removes_unknown_rows(self):
        stale = AlertProcedureTemplate.objects.create(
            alert_type=ALERT_TYPE_MANUAL, name="stale", description="d", response_time_hours=1
        )
        AlertProcedureStep.objects.create(template=stale, order=1, description="stale step")

        summary = run("sync_procedure_templates")
        self.assertIn("Templates: 22 created, 0 updated, 1 deleted | Steps: 169 created, 0 updated", summary)
        self.assertEqual(AlertProcedureTemplate.objects.count(), len(PROCEDURE_TEMPLATES))
        self.assertEqual(AlertProcedureStep.objects.count(), sum(len(t["steps"]) for t in PROCEDURE_TEMPLATES))
        sanctions = AlertProcedureTemplate.objects.get(alert_type="sanctions_match")
        self.assertEqual(sanctions.priority, "critical")
        self.assertEqual(sanctions.steps.count(), 10)
        self.assertFalse(sanctions.customer_notification_allowed)

        AlertProcedureStep.objects.create(template=sanctions, order=99, description="added by hand")
        sanctions.name = "edited by hand"
        sanctions.save()

        summary = run("sync_procedure_templates")
        self.assertIn("Templates: 0 created, 22 updated, 0 deleted | Steps: 0 created, 169 updated", summary)
        sanctions.refresh_from_db()
        self.assertEqual(sanctions.name, "Sanctions Match")
        self.assertFalse(sanctions.steps.filter(order=99).exists())
        self.assertEqual(AlertProcedureStep.objects.count(), 169)
        self.assertEqual(PROCEDURE_TEMPLATES[0]["alert_type"], "sanctions_match")
        self.assertEqual(PROCEDURE_TEMPLATES[0]["steps"][0]["order"], 1)
