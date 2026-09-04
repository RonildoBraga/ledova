import json

from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from compliance.admin._helpers import (
    GREEN,
    RED,
    YELLOW,
    admin_link,
    choice_badge,
    short_hex,
)
from compliance.constants import SCREENING_STATUS_FAILED
from compliance.models import ComplianceAlert, TransactionScreening
from compliance.services.crypto_screening import CryptoScreeningService

SCREENING_STATUS_COLOURS = {"pending": YELLOW, "completed": GREEN, "failed": RED}
SCREENING_RESULT_COLOURS = {"approved": GREEN, "review": YELLOW, "rejected": RED}
RISK_LEVEL_COLOURS = {"LOW": GREEN, "MEDIUM": YELLOW, "HIGH": RED}


@admin.register(TransactionScreening)
class TransactionScreeningAdmin(admin.ModelAdmin):
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
    list_filter = ["status", "result", "risk_level", "provider", ("user_account", admin.RelatedOnlyFieldListFilter)]
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
    actions = ["retry_failed_screenings"]
    # The raw transaction/user_account FKs are replaced by links: the selects would list every row.
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "transaction_link",
                    "user_account_link",
                    "provider",
                    "provider_transaction_id",
                    "to_address",
                    "from_address",
                )
            },
        ),
        ("Screening Result", {"fields": ("status", "result", "risk_score", "risk_level", "risk_signals_display")}),
        ("Error & Retry", {"fields": ("error_message", "retry_count")}),
        ("Related Alerts", {"fields": ("related_alerts",)}),
        (
            "Timestamps",
            {"fields": ("submitted_at", "completed_at", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
        ("Raw API Response", {"fields": ("raw_response_display",), "classes": ("collapse",)}),
        ("System Information", {"fields": ("uuid",), "classes": ("collapse",)}),
    )

    @admin.display(description="To Address")
    def to_address_short(self, obj):
        return short_hex(obj.to_address)

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return choice_badge(obj.status, SCREENING_STATUS_COLOURS)

    @admin.display(description="Result", ordering="result")
    def result_badge(self, obj):
        return choice_badge(obj.result, SCREENING_RESULT_COLOURS)

    @admin.display(description="Risk Level", ordering="risk_level")
    def risk_level_badge(self, obj):
        return choice_badge(obj.risk_level, RISK_LEVEL_COLOURS)

    @admin.display(description="Transaction")
    def transaction_link(self, obj):
        return admin_link(obj.transaction)

    @admin.display(description="User Account")
    def user_account_link(self, obj):
        return admin_link(obj.user_account, obj.user_account.account_number or str(obj.user_account))

    @admin.display(description="Related Alerts")
    def related_alerts(self, obj):
        alerts = ComplianceAlert.objects.filter(alert_data__screening_id=str(obj.uuid))[:5]
        if not alerts:
            return "No alerts"
        return format_html_join(
            mark_safe("<br>"),
            "{}",
            ((admin_link(alert, f"{alert.triggered_rule} - {alert.alert_type} ({alert.status})"),) for alert in alerts),
        )

    @admin.display(description="Risk Signals")
    def risk_signals_display(self, obj):
        if not obj.risk_signals:
            return "None detected"
        if isinstance(obj.risk_signals, list):
            items = format_html_join("", "<li>{}</li>", ((signal,) for signal in obj.risk_signals))
            return format_html("<ul style='margin: 0; padding-left: 20px;'>{}</ul>", items)
        return str(obj.risk_signals)

    @admin.display(description="Raw API Response")
    def raw_response_display(self, obj):
        if not obj.raw_response:
            return "No response data"
        try:
            formatted = json.dumps(obj.raw_response, indent=2)
        except (TypeError, ValueError):
            return str(obj.raw_response)
        return format_html(
            '<pre style="max-height: 400px; overflow: auto; background: #f5f5f5; padding: 10px; '
            'border-radius: 4px;">{}</pre>',
            formatted,
        )

    @admin.action(description="Retry failed screenings")
    def retry_failed_screenings(self, request, queryset):
        failed = list(queryset.filter(status=SCREENING_STATUS_FAILED))
        if not failed:
            self.message_user(request, "No failed screenings selected.", level="warning")
            return
        service = CryptoScreeningService()
        results = [service.retry_failed_screening(screening) for screening in failed]
        still_failed = sum(result.status == SCREENING_STATUS_FAILED for result in results)
        self.message_user(
            request,
            f"Retried {len(failed)} screening(s): {len(failed) - still_failed} succeeded, {still_failed} still failed.",
        )
