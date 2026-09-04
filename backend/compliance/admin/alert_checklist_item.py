from django.contrib import admin

from compliance.admin._helpers import GREEN, GREY, RED, YELLOW, admin_link, badge
from compliance.models import AlertChecklistItem


@admin.register(AlertChecklistItem)
class AlertChecklistItemAdmin(admin.ModelAdmin):
    list_display = ["step_description", "alert_link", "status_badge", "completed_by", "completed_at", "has_notes"]
    list_filter = [
        "is_completed",
        "is_skipped",
        ("completed_by", admin.RelatedOnlyFieldListFilter),
        ("alert__alert_type", admin.AllValuesFieldListFilter),
    ]
    search_fields = ["alert__triggered_rule", "alert__user_account__account_number", "step__description", "notes"]
    readonly_fields = ["uuid", "created_at", "updated_at", "alert_link", "step_info", "is_overdue_display"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    autocomplete_fields = ["alert", "completed_by"]
    actions = ["mark_completed", "mark_skipped"]

    @admin.display(description="Step", ordering="step__order")
    def step_description(self, obj):
        return f"Step {obj.step.order}: {obj.step.description[:40]}"

    @admin.display(description="Alert")
    def alert_link(self, obj):
        return admin_link(obj.alert, f"{obj.alert.triggered_rule} - {obj.alert.alert_type}")

    @admin.display(description="Step Requirements")
    def step_info(self, obj):
        required = "Required" if obj.step.is_required else "Optional"
        return f"{required} (Condition: {obj.step.condition})" if obj.step.condition else required

    @admin.display(description="Status")
    def status_badge(self, obj):
        if obj.is_completed:
            return badge("COMPLETED", GREEN)
        if obj.is_skipped:
            return badge("SKIPPED", GREY)
        if obj.is_overdue:
            return badge("OVERDUE", RED)
        return badge("PENDING", YELLOW)

    @admin.display(description="Notes", boolean=True)
    def has_notes(self, obj):
        return bool(obj.notes)

    @admin.display(description="Overdue", boolean=True)
    def is_overdue_display(self, obj):
        return obj.is_overdue

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
            is_skipped=True, skip_reason="Bulk skipped via admin"
        )
        self.message_user(request, f"{count} item(s) marked as skipped.")
