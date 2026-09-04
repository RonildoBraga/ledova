from django.contrib import admin

from compliance.admin._helpers import GREEN, GREY, SEVERITY_COLOURS, badge, choice_badge
from compliance.models import MonitoringRule


@admin.register(MonitoringRule)
class MonitoringRuleAdmin(admin.ModelAdmin):
    list_display = ["rule_code", "name", "rule_type", "severity_badge", "status_badge", "created_at"]
    list_filter = ["is_active", "rule_type", "alert_severity"]
    search_fields = ["rule_code", "name", "description"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    ordering = ["rule_code"]
    fieldsets = (
        (None, {"fields": ("rule_code", "name", "description")}),
        (
            "Rule Configuration",
            {
                "fields": ("rule_type", "parameters"),
                "description": "Configure rule-specific parameters as JSON. "
                "Examples: {'amount': 10000} for threshold, "
                "{'max_transactions': 5, 'period_minutes': 60} for rapid transactions.",
            },
        ),
        ("Alert Settings", {"fields": ("alert_severity", "is_active")}),
        ("System Information", {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Severity", ordering="alert_severity")
    def severity_badge(self, obj):
        return choice_badge(obj.alert_severity, SEVERITY_COLOURS)

    @admin.display(description="Status", ordering="is_active")
    def status_badge(self, obj):
        return badge("ACTIVE", GREEN) if obj.is_active else badge("INACTIVE", GREY)
