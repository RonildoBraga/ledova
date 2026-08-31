"""
Admin package for compliance app.
"""

from compliance.admin.alert_checklist_item import AlertChecklistItemAdmin
from compliance.admin.alert_procedure_step import AlertProcedureStepAdmin
from compliance.admin.alert_procedure_template import AlertProcedureTemplateAdmin
from compliance.admin.compliance_alert import ComplianceAlertAdmin
from compliance.admin.customer_risk_assessment import CustomerRiskAssessmentAdmin
from compliance.admin.monitoring_rule import MonitoringRuleAdmin
from compliance.admin.transaction_screening import TransactionScreeningAdmin

__all__ = [
    "AlertChecklistItemAdmin",
    "AlertProcedureStepAdmin",
    "AlertProcedureTemplateAdmin",
    "ComplianceAlertAdmin",
    "CustomerRiskAssessmentAdmin",
    "MonitoringRuleAdmin",
    "TransactionScreeningAdmin",
]
