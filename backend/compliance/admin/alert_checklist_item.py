from django.contrib import admin
from django.utils.html import format_html

from compliance.models import AlertChecklistItem


@admin.register(AlertChecklistItem)
class AlertChecklistItemAdmin(admin.ModelAdmin):
    """
    Admin for alert checklist items.

    Allows AML Compliance Officer to:
    - Track completion of procedure steps for each alert
    - View audit trail of who completed each step
    - Add notes and evidence references
    """

    list_display = [
        "step_description",
        "alert_link",
        "status_badge",
        "completed_by",
        "completed_at",
        "has_notes",
    ]
    list_filter = [
        "is_completed",
        "is_skipped",
        ("completed_by", admin.RelatedOnlyFieldListFilter),
        ("alert__alert_type", admin.AllValuesFieldListFilter),
    ]
    search_fields = [
        "alert__triggered_rule",
        "alert__user_account__account_number",
        "step__description",
        "notes",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "alert_link",
        "step_info",
        "is_overdue_display",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    autocomplete_fields = ["alert", "completed_by"]

    fieldsets = (
        (
            "Alert & Step",
            {
                "fields": (
                    "alert",
                    "alert_link",
                    "step",
                    "step_info",
                ),
            },
        ),
        (
            "Completion Status",
            {
                "fields": (
                    "is_completed",
                    "completed_at",
                    "completed_by",
                    "is_overdue_display",
                ),
            },
        ),
        (
            "Skip Information",
            {
                "fields": (
                    "is_skipped",
                    "skip_reason",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Notes & Evidence",
            {
                "fields": (
                    "notes",
                    "evidence_references",
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

    actions = ["mark_completed", "mark_skipped"]

    def step_description(self, obj):
        return f"Step {obj.step.order}: {obj.step.description[:40]}"

    step_description.short_description = "Step"
    step_description.admin_order_field = "step__order"

    def alert_link(self, obj):
        return format_html(
            '<a href="/admin/compliance/compliancealert/{}/change/">{} - {}</a>',
            obj.alert.uuid,
            obj.alert.triggered_rule,
            obj.alert.alert_type,
        )

    alert_link.short_description = "Alert"

    def step_info(self, obj):
        required = "Required" if obj.step.is_required else "Optional"
        condition = f" (Condition: {obj.step.condition})" if obj.step.condition else ""
        return f"{required}{condition}"

    step_info.short_description = "Step Requirements"

    def status_badge(self, obj):
        if obj.is_completed:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">COMPLETED</span>'
            )
        if obj.is_skipped:
            return format_html(
                '<span style="background-color: #6c757d; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">SKIPPED</span>'
            )
        if obj.is_overdue:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 2px 8px; '
                'border-radius: 4px; font-size: 11px;">OVERDUE</span>'
            )
        return format_html(
            '<span style="background-color: #ffc107; color: black; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">PENDING</span>'
        )

    status_badge.short_description = "Status"

    def has_notes(self, obj):
        return bool(obj.notes)

    has_notes.short_description = "Notes"
    has_notes.boolean = True

    def is_overdue_display(self, obj):
        return obj.is_overdue

    is_overdue_display.short_description = "Overdue"
    is_overdue_display.boolean = True

    @admin.action(description="Mark selected items as completed")
    def mark_completed(self, request, queryset):
        count = 0
        for item in queryset.filter(is_completed=False):
            item.mark_completed(request.user)
            count += 1
        self.message_user(request, f"{count} item(s) marked as completed.")

    @admin.action(description="Mark selected items as skipped")
    def mark_skipped(self, request, queryset):
        count = queryset.filter(is_completed=False, is_skipped=False).update(
            is_skipped=True,
            skip_reason="Bulk skipped via admin",
        )
        self.message_user(request, f"{count} item(s) marked as skipped.")
