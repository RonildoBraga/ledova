"""
Admin for MonitoringRule model.
"""

from django.contrib import admin
from django.utils.html import format_html

from compliance.models import MonitoringRule


@admin.register(MonitoringRule)
class MonitoringRuleAdmin(admin.ModelAdmin):
    """
    Admin for configurable transaction monitoring rules.

    Allows AML Compliance Officer to:
    - View and manage monitoring rules
    - Configure rule parameters (thresholds, timeframes)
    - Enable/disable rules
    """

    list_display = [
        "rule_code",
        "name",
        "rule_type",
        "severity_badge",
        "status_badge",
        "created_at",
    ]
    list_filter = ["is_active", "rule_type", "alert_severity"]
    search_fields = ["rule_code", "name", "description"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    ordering = ["rule_code"]

    fieldsets = (
        (
            "Rule Identification",
            {
                "fields": ("rule_code", "name", "description"),
            },
        ),
        (
            "Rule Configuration",
            {
                "fields": ("rule_type", "parameters"),
                "description": "Configure rule-specific parameters as JSON. "
                "Examples: {'amount': 10000} for threshold, "
                "{'max_transactions': 5, 'period_minutes': 60} for rapid transactions.",
            },
        ),
        (
            "Alert Settings",
            {
                "fields": ("alert_severity", "is_active"),
            },
        ),
        (
            "System Information",
            {
                "fields": ("uuid", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def severity_badge(self, obj):
        """Display severity as a colored badge."""
        colors = {
            "low": "#28a745",
            "medium": "#ffc107",
            "high": "#fd7e14",
            "critical": "#dc3545",
        }
        color = colors.get(obj.alert_severity, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.alert_severity.upper(),
        )

    severity_badge.short_description = "Severity"
    severity_badge.admin_order_field = "alert_severity"

    def status_badge(self, obj):
        """Display active/inactive status as a badge."""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">ACTIVE</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">INACTIVE</span>'
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "is_active"
