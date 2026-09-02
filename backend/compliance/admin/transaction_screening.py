from django.contrib import admin
from django.utils.html import format_html

from compliance.constants import SCREENING_STATUS_FAILED
from compliance.models import TransactionScreening
from compliance.services.crypto_screening import CryptoScreeningService


@admin.register(TransactionScreening)
class TransactionScreeningAdmin(admin.ModelAdmin):
    """
    Admin for transaction screening records.

    Allows AML Compliance Officer to:
    - View blockchain analytics screening results
    - Monitor failed screenings and retry them
    - Review risk scores and signals
    - Navigate to related transactions and alerts
    """

    list_display = [
        "provider_transaction_id",
        "provider",
        "user_account",
        "to_address_short",
        "status_badge",
        "result_badge",
        "risk_level_badge",
        "risk_score",
        "retry_count",
        "created_at",
    ]
    list_filter = [
        "status",
        "result",
        "risk_level",
        "provider",
        ("user_account", admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = [
        "provider_transaction_id",
        "to_address",
        "from_address",
        "user_account__account_number",
        "user_account__uuid",
    ]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "submitted_at",
        "completed_at",
        "transaction_link",
        "user_account_link",
        "related_alerts",
        "risk_signals_display",
        "raw_response_display",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Screening Information",
            {
                "fields": (
                    "transaction_link",
                    "user_account_link",
                    "provider",
                    "provider_transaction_id",
                    "to_address",
                    "from_address",
                ),
            },
        ),
        (
            "Screening Result",
            {
                "fields": (
                    "status",
                    "result",
                    "risk_score",
                    "risk_level",
                    "risk_signals_display",
                ),
            },
        ),
        (
            "Error & Retry",
            {
                "fields": (
                    "error_message",
                    "retry_count",
                ),
            },
        ),
        (
            "Related Alerts",
            {
                "fields": ("related_alerts",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "submitted_at",
                    "completed_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Raw API Response",
            {
                "fields": ("raw_response_display",),
                "classes": ("collapse",),
            },
        ),
        (
            "System Information",
            {
                "fields": ("uuid",),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["retry_failed_screenings"]

    def to_address_short(self, obj):
        if obj.to_address:
            return f"{obj.to_address[:10]}...{obj.to_address[-8:]}"
        return "-"

    to_address_short.short_description = "To Address"

    def status_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "completed": "#28a745",
            "failed": "#dc3545",
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

    def result_badge(self, obj):
        if not obj.result:
            return "-"
        colors = {
            "approved": "#28a745",
            "review": "#ffc107",
            "rejected": "#dc3545",
        }
        color = colors.get(obj.result, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.result.upper(),
        )

    result_badge.short_description = "Result"
    result_badge.admin_order_field = "result"

    def risk_level_badge(self, obj):
        if not obj.risk_level:
            return "-"
        colors = {
            "LOW": "#28a745",
            "MEDIUM": "#ffc107",
            "HIGH": "#dc3545",
        }
        color = colors.get(obj.risk_level, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.risk_level,
        )

    risk_level_badge.short_description = "Risk Level"
    risk_level_badge.admin_order_field = "risk_level"

    def transaction_link(self, obj):
        if obj.transaction:
            return format_html(
                '<a href="/admin/wallets/transaction/{}/change/">{}</a>',
                obj.transaction.uuid,
                str(obj.transaction)[:50],
            )
        return "-"

    transaction_link.short_description = "Transaction"

    def user_account_link(self, obj):
        if obj.user_account:
            return format_html(
                '<a href="/admin/users/useraccount/{}/change/">{}</a>',
                obj.user_account.uuid,
                obj.user_account.account_number or str(obj.user_account),
            )
        return "-"

    user_account_link.short_description = "User Account"

    def related_alerts(self, obj):
        from compliance.models import ComplianceAlert

        alerts = ComplianceAlert.objects.filter(alert_data__screening_id=str(obj.uuid)).select_related()

        if not alerts.exists():
            return "No alerts"

        links = []
        for alert in alerts[:5]:
            links.append(
                format_html(
                    '<a href="/admin/compliance/compliancealert/{}/change/">' "{} - {} ({})</a>",
                    alert.uuid,
                    alert.triggered_rule,
                    alert.alert_type,
                    alert.status,
                )
            )
        return format_html("<br>".join(links))

    related_alerts.short_description = "Related Alerts"

    def risk_signals_display(self, obj):
        if not obj.risk_signals:
            return "None detected"

        signals = obj.risk_signals
        if isinstance(signals, list):
            items = "".join(f"<li>{signal}</li>" for signal in signals)
            return format_html(f"<ul style='margin: 0; padding-left: 20px;'>{items}</ul>")
        return str(signals)

    risk_signals_display.short_description = "Risk Signals"

    def raw_response_display(self, obj):
        import json

        if not obj.raw_response:
            return "No response data"

        try:
            formatted = json.dumps(obj.raw_response, indent=2)
            return format_html(
                '<pre style="max-height: 400px; overflow: auto; '
                'background: #f5f5f5; padding: 10px; border-radius: 4px;">{}</pre>',
                formatted,
            )
        except Exception:
            return str(obj.raw_response)

    raw_response_display.short_description = "Raw API Response"

    @admin.action(description="Retry failed screenings")
    def retry_failed_screenings(self, request, queryset):
        failed_screenings = queryset.filter(status=SCREENING_STATUS_FAILED)
        count = failed_screenings.count()

        if count == 0:
            self.message_user(request, "No failed screenings selected.", level="warning")
            return

        service = CryptoScreeningService()
        success_count = 0
        still_failed = 0

        for screening in failed_screenings:
            result = service.retry_failed_screening(screening)
            if result.status != SCREENING_STATUS_FAILED:
                success_count += 1
            else:
                still_failed += 1

        self.message_user(
            request,
            f"Retried {count} screening(s): {success_count} succeeded, {still_failed} still failed.",
        )
