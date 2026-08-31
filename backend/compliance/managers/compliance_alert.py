"""
Manager for ComplianceAlert model.
"""

from django.db import models

from compliance.querysets.compliance_alert import ComplianceAlertQuerySet


class ComplianceAlertManager(models.Manager.from_queryset(ComplianceAlertQuerySet)):
    """Manager for ComplianceAlert with custom convenience methods."""

    def has_open_for_user_account(self, user_account) -> bool:
        """Check if a user account has any open compliance alerts."""
        return self.for_user_account(user_account).open().exists()

    def has_active_hold_for_user_account(self, user_account) -> bool:
        """Check if a user account has any active compliance holds."""
        return self.for_user_account(user_account).with_active_hold().exists()
