from django.contrib import admin

from compliance.admin._helpers import (
    GREEN,
    ORANGE,
    RED,
    SEVERITY_COLOURS,
    YELLOW,
    choice_badge,
)
from compliance.models import AlertProcedureStep, AlertProcedureTemplate

SMR_REQUIREMENT_COLOURS = {"mandatory": RED, "likely": ORANGE, "assess": YELLOW, "unlikely": GREEN}


class AlertProcedureStepInline(admin.TabularInline):
    model = AlertProcedureStep
    extra = 0
    ordering = ["order"]
    fields = ["order", "description", "is_required", "condition", "policy_reference"]


@admin.register(AlertProcedureTemplate)
class AlertProcedureTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "alert_type",
        "priority_badge",
        "response_time_display",
        "smr_requirement_badge",
        "escalation_required",
        "step_count",
        "is_active",
    ]
    list_filter = ["priority", "smr_requirement", "escalation_required", "is_active", "alert_type"]
    search_fields = ["name", "alert_type", "description"]
    readonly_fields = ["uuid", "created_at", "updated_at", "step_count", "required_step_count"]
    ordering = ["priority", "alert_type"]
    inlines = [AlertProcedureStepInline]

    @admin.display(description="Priority", ordering="priority")
    def priority_badge(self, obj):
        return choice_badge(obj.priority, SEVERITY_COLOURS)

    @admin.display(description="SMR", ordering="smr_requirement")
    def smr_requirement_badge(self, obj):
        return choice_badge(obj.smr_requirement, SMR_REQUIREMENT_COLOURS)

    @admin.display(description="Response Time", ordering="response_time_hours")
    def response_time_display(self, obj):
        days, hours = divmod(obj.response_time_hours, 24)
        if not days:
            return f"{hours}h"
        return f"{days}d {hours}h" if hours else f"{days}d"
