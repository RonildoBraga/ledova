"""
Manager for AlertProcedureTemplate model.
"""

from django.db import models

from compliance.querysets.alert_procedure_template import AlertProcedureTemplateQuerySet


class AlertProcedureTemplateManager(models.Manager.from_queryset(AlertProcedureTemplateQuerySet)):
    """Manager for AlertProcedureTemplate with custom convenience methods."""

    def get_for_alert(self, alert):
        """
        Get the procedure template for a given alert.

        Args:
            alert: ComplianceAlert instance

        Returns:
            AlertProcedureTemplate instance or None if no template exists.
        """
        return self.active().filter(alert_type=alert.alert_type).first()
