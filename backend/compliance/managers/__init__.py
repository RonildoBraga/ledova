"""
Managers package for compliance app.

Only managers with custom logic beyond queryset delegation are kept here.
Pure-proxy managers have been removed — models use QuerySet.as_manager() directly.
"""

from compliance.managers.alert_checklist_item import AlertChecklistItemManager
from compliance.managers.alert_procedure_template import AlertProcedureTemplateManager
from compliance.managers.compliance_alert import ComplianceAlertManager

__all__ = [
    "AlertChecklistItemManager",
    "AlertProcedureTemplateManager",
    "ComplianceAlertManager",
]
