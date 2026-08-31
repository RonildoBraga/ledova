"""
Admin for ComplianceAlert model.
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from compliance.models import AlertChecklistItem, ComplianceAlert


class AlertChecklistItemInline(admin.TabularInline):
    """Inline for checklist items on the alert page."""

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

    def step_order(self, obj):
        return f"Step {obj.step.order}"

    step_order.short_description = "#"

    def step_description(self, obj):
        return obj.step.description

    step_description.short_description = "Description"

    def is_required_badge(self, obj):
        if obj.step.is_required:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 2px 6px; '
                'border-radius: 4px; font-size: 10px;">Required</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 2px 6px; '
            'border-radius: 4px; font-size: 10px;">Optional</span>'
        )

    is_required_badge.short_description = "Type"

    def status_badge(self, obj):
        if obj.is_completed:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                'border-radius: 4px; font-size: 10px;">✓ Completed</span>'
            )
        elif obj.is_skipped:
            return format_html(
                '<span style="background-color: #6c757d; color: white; padding: 2px 6px; '
                'border-radius: 4px; font-size: 10px;">⊘ Skipped</span>'
            )
        return format_html(
            '<span style="background-color: #ffc107; color: black; padding: 2px 6px; '
            'border-radius: 4px; font-size: 10px;">☐ Pending</span>'
        )

    status_badge.short_description = "Status"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ComplianceAlert)
class ComplianceAlertAdmin(admin.ModelAdmin):
    """
    Admin for compliance alerts.

    Allows AML Compliance Officer to:
    - View alerts triggered by monitoring rules
    - Assign alerts to team members
    - Track alert status and resolution
    - Navigate to related transactions and investigations
    """

    list_display = [
        "triggered_rule",
        "user_account",
        "alert_type",
        "severity_badge",
        "status_badge",
        "assigned_to",
        "smr_badge",
        "slack_badge",
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
    search_fields = [
        "triggered_rule",
        "description",
        "user_account__account_number",
        "user_account__uuid",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "monitoring_rule",
        "transaction_link",
        "fiat_transaction_link",
        "slack_channel_id",
        "slack_thread_ts",
        "internal-assistant_notified_at",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    inlines = [AlertChecklistItemInline]

    fieldsets = (
        (
            "Alert Information",
            {
                "fields": (
                    "user_account",
                    "triggered_rule",
                    "alert_type",
                    "severity",
                    "description",
                    "alert_data",
                ),
            },
        ),
        (
            "Related Transactions",
            {
                "fields": (
                    "transaction_link",
                    "fiat_transaction_link",
                    "monitoring_rule",
                ),
            },
        ),
        (
            "Status & Assignment",
            {
                "fields": (
                    "status",
                    "assigned_to",
                    "assigned_at",
                ),
            },
        ),
        (
            "Resolution",
            {
                "fields": (
                    "investigation_outcome",
                    "resolution_notes",
                    "resolved_at",
                    "resolved_by",
                ),
            },
        ),
        (
            "SMR (Suspicious Matter Report)",
            {
                "fields": (
                    "smr_required",
                    "smr_type",
                    "smr_reference",
                    "smr_filed_at",
                ),
                "description": "Record SMR details after filing in AUSTRAC portal",
            },
        ),
        (
            "Account Action",
            {
                "fields": (
                    "account_action",
                    "account_action_at",
                ),
            },
        ),
        (
            "internal-assistant Slack Notification",
            {
                "fields": (
                    "slack_channel_id",
                    "slack_thread_ts",
                    "internal-assistant_notified_at",
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

    actions = ["assign_to_me", "mark_as_reviewing", "close_alerts"]

    def severity_badge(self, obj):
        """Display severity as a colored badge."""
        colors = {
            "low": "#28a745",
            "medium": "#ffc107",
            "high": "#fd7e14",
            "critical": "#dc3545",
        }
        color = colors.get(obj.severity, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.severity.upper(),
        )

    severity_badge.short_description = "Severity"
    severity_badge.admin_order_field = "severity"

    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            "new": "#17a2b8",
            "reviewing": "#ffc107",
            "escalated": "#fd7e14",
            "closed": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def smr_badge(self, obj):
        """Display SMR status as a badge."""
        if obj.smr_required:
            if obj.smr_filed_at:
                return format_html(
                    '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                    'border-radius: 4px; font-size: 10px;">✓ Filed</span>'
                )
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 2px 6px; '
                'border-radius: 4px; font-size: 10px;">⚠ Pending</span>'
            )
        return "-"

    smr_badge.short_description = "SMR"

    def slack_badge(self, obj):
        """Display internal-assistant Slack delivery status."""
        if obj.slack_thread_ts:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 2px 6px; '
                'border-radius: 4px; font-size: 10px;">Posted</span>'
            )
        return "-"

    slack_badge.short_description = "Slack"

    def transaction_link(self, obj):
        """Link to related crypto transaction."""
        if obj.transaction:
            return format_html(
                '<a href="/admin/wallets/transaction/{}/change/">{}</a>',
                obj.transaction.uuid,
                str(obj.transaction)[:50],
            )
        return "-"

    transaction_link.short_description = "Crypto Transaction"

    def fiat_transaction_link(self, obj):
        """Link to related fiat transaction."""
        if obj.fiat_transaction:
            return format_html(
                '<a href="/admin/wallets/fiattransaction/{}/change/">{}</a>',
                obj.fiat_transaction.uuid,
                str(obj.fiat_transaction)[:50],
            )
        return "-"

    fiat_transaction_link.short_description = "Fiat Transaction"

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
        count = queryset.update(
            status="closed",
            resolved_at=timezone.now(),
            resolved_by=request.user,
        )
        self.message_user(request, f"{count} alert(s) closed.")
