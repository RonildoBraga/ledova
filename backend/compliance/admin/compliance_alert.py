from django.contrib import admin
from django.utils import timezone

from compliance.admin._helpers import (
    GREEN,
    GREY,
    ORANGE,
    RED,
    SEVERITY_COLOURS,
    TEAL,
    YELLOW,
    admin_link,
    badge,
    choice_badge,
)
from compliance.models import AlertChecklistItem, ComplianceAlert

ALERT_STATUS_COLOURS = {"new": TEAL, "reviewing": YELLOW, "escalated": ORANGE, "closed": GREY}


class AlertChecklistItemInline(admin.TabularInline):
    model = AlertChecklistItem
    extra = 0
    can_delete = False
    ordering = ["step__order"]
    fields = [
        "step_order",
        "step_description",
        "is_required_badge",
        "status_badge",
        "completed_by",
        "completed_at",
        "notes",
    ]
    readonly_fields = [
        "step_order",
        "step_description",
        "is_required_badge",
        "status_badge",
        "completed_by",
        "completed_at",
    ]

    @admin.display(description="#")
    def step_order(self, obj):
        return f"Step {obj.step.order}"

    @admin.display(description="Description")
    def step_description(self, obj):
        return obj.step.description

    @admin.display(description="Type")
    def is_required_badge(self, obj):
        return badge("Required", RED) if obj.step.is_required else badge("Optional", GREY)

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.is_completed:
            return badge("✓ Completed", GREEN)
        if obj.is_skipped:
            return badge("⊘ Skipped", GREY)
        return badge("☐ Pending", YELLOW)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ComplianceAlert)
class ComplianceAlertAdmin(admin.ModelAdmin):
    list_display = [
        "triggered_rule",
        "user_account",
        "alert_type",
        "severity_badge",
        "status_badge",
        "assigned_to",
        "smr_badge",
        "created_at",
    ]
    list_filter = [
        "status",
        "severity",
        "alert_type",
        "triggered_rule",
        "smr_required",
        "account_action",
        ("assigned_to", admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ["triggered_rule", "description", "user_account__account_number", "user_account__uuid"]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "monitoring_rule",
        "transaction_link",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    inlines = [AlertChecklistItemInline]
    actions = ["assign_to_me", "mark_as_reviewing", "close_alerts"]

    fieldsets = (
        (None, {"fields": ("user_account", "triggered_rule", "alert_type", "severity", "description", "alert_data")}),
        ("Related Transactions", {"fields": ("transaction_link", "monitoring_rule")}),
        ("Status & Assignment", {"fields": ("status", "assigned_to", "assigned_at")}),
        ("Resolution", {"fields": ("investigation_outcome", "resolution_notes", "resolved_at", "resolved_by")}),
        (
            "SMR (Suspicious Matter Report)",
            {
                "fields": ("smr_required", "smr_type", "smr_reference", "smr_filed_at"),
                "description": "Record SMR details after filing in AUSTRAC portal",
            },
        ),
        ("Account Action", {"fields": ("account_action", "account_action_at")}),
        ("System Information", {"fields": ("uuid", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Severity", ordering="severity")
    def severity_badge(self, obj):
        return choice_badge(obj.severity, SEVERITY_COLOURS)

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return choice_badge(obj.status, ALERT_STATUS_COLOURS)

    @admin.display(description="SMR")
    def smr_badge(self, obj):
        if not obj.smr_required:
            return "-"
        return badge("✓ Filed", GREEN) if obj.smr_filed_at else badge("⚠ Pending", RED)

    @admin.display(description="Crypto Transaction")
    def transaction_link(self, obj):
        return admin_link(obj.transaction)

    @admin.action(description="Assign selected alerts to me")
    def assign_to_me(self, request, queryset):
        count = queryset.update(assigned_to=request.user, assigned_at=timezone.now())
        self.message_user(request, f"{count} alert(s) assigned to you.")

    @admin.action(description="Mark selected alerts as reviewing")
    def mark_as_reviewing(self, request, queryset):
        count = queryset.update(status="reviewing")
        self.message_user(request, f"{count} alert(s) marked as reviewing.")

    @admin.action(description="Close selected alerts")
    def close_alerts(self, request, queryset):
        count = queryset.update(status="closed", resolved_at=timezone.now(), resolved_by=request.user)
        self.message_user(request, f"{count} alert(s) closed.")
