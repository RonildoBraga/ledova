from django.contrib import admin
from django.utils.html import format_html

from compliance.models import AlertProcedureTemplate


class AlertProcedureStepInline(admin.TabularInline):
    model = AlertProcedureTemplate.steps.rel.related_model
    extra = 0
    ordering = ["order"]
    fields = ["order", "description", "is_required", "condition", "policy_reference"]
    readonly_fields = []


@admin.register(AlertProcedureTemplate)
class AlertProcedureTemplateAdmin(admin.ModelAdmin):
    """
    Admin for alert procedure templates.

    Allows AML Compliance Officer to:
    - Define procedure templates for each alert type
    - Configure response times, SMR requirements, and escalation rules
    - Manage procedure steps
    """

    list_display = [
        "name",
        "alert_type",
        "priority_badge",
        "response_time_display",
        "smr_requirement_badge",
        "escalation_required",
        "step_count_display",
        "is_active",
    ]
    list_filter = [
        "priority",
        "smr_requirement",
        "escalation_required",
        "is_active",
        "alert_type",
    ]
    search_fields = [
        "name",
        "alert_type",
        "description",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "step_count_display",
        "required_step_count_display",
    ]
    ordering = ["priority", "alert_type"]
    inlines = [AlertProcedureStepInline]

    fieldsets = (
        (
            "Template Information",
            {
                "fields": (
                    "alert_type",
                    "name",
                    "description",
                    "is_active",
                ),
            },
        ),
        (
            "Priority & Response Time",
            {
                "fields": (
                    "priority",
                    "response_time_hours",
                ),
            },
        ),
        (
            "SMR Requirements",
            {
                "fields": (
                    "smr_requirement",
                    "smr_timeframe_hours",
                ),
            },
        ),
        (
            "Escalation",
            {
                "fields": (
                    "escalation_required",
                    "escalation_timeframe",
                ),
            },
        ),
        (
            "Customer Notification",
            {
                "fields": ("customer_notification_allowed",),
                "description": "Set to False for alerts with tipping-off risk (e.g., SMR-related).",
            },
        ),
        (
            "Policy & Documentation",
            {
                "fields": (
                    "policy_references",
                    "required_documentation",
                    "outcome_options",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "step_count_display",
                    "required_step_count_display",
                ),
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

    def priority_badge(self, obj):
        colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
        }
        color = colors.get(obj.priority, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.priority.upper(),
        )

    priority_badge.short_description = "Priority"
    priority_badge.admin_order_field = "priority"

    def smr_requirement_badge(self, obj):
        colors = {
            "mandatory": "#dc3545",
            "likely": "#fd7e14",
            "assess": "#ffc107",
            "unlikely": "#28a745",
        }
        color = colors.get(obj.smr_requirement, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.smr_requirement.upper(),
        )

    smr_requirement_badge.short_description = "SMR"
    smr_requirement_badge.admin_order_field = "smr_requirement"

    def response_time_display(self, obj):
        hours = obj.response_time_hours
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        remaining_hours = hours % 24
        if remaining_hours:
            return f"{days}d {remaining_hours}h"
        return f"{days}d"

    response_time_display.short_description = "Response Time"
    response_time_display.admin_order_field = "response_time_hours"

    def step_count_display(self, obj):
        return obj.step_count

    step_count_display.short_description = "Total Steps"

    def required_step_count_display(self, obj):
        return obj.required_step_count

    required_step_count_display.short_description = "Required Steps"
