"""Background tasks for compliance (AML/CTF).

- run_batch_monitoring: hourly pattern-rule sweep over recent transactions.
- check_periodic_reviews: daily flag of risk assessments overdue for 24-month review.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from compliance.constants import BATCH_MONITORING_LOOKBACK_HOURS

logger = logging.getLogger("ledova_backend")


@app.periodic(cron="0 * * * *")
@app.task(
    name="compliance.tasks.run_batch_monitoring",
    retry=RetryStrategy(max_attempts=4, wait=60),
)
def run_batch_monitoring(timestamp: int) -> str:
    """Run batch pattern-rule monitoring over recent transactions.

    Some AML/CTF patterns (velocity, structuring) require historical analysis and may
    flag transactions that individually looked fine.
    """
    from compliance.models import MonitoringRule
    from compliance.services.transaction_monitoring import TransactionMonitoringService
    from users.models import UserAccount

    active_pattern_rules = MonitoringRule.objects.active().pattern_rules()

    if not active_pattern_rules.exists():
        logger.info("[BATCH_MONITORING] No active pattern rules to check")
        return "No active pattern rules"

    recent = timezone.now() - timedelta(hours=BATCH_MONITORING_LOOKBACK_HOURS)

    from wallets.models import Transaction

    active_account_uuids = (
        Transaction.objects.filter(created_at__gte=recent).values_list("wallet__user_account", flat=True).distinct()
    )
    active_accounts = UserAccount.objects.filter(uuid__in=active_account_uuids)

    alerts_created = 0
    accounts_checked = 0

    for account in active_accounts:
        try:
            alerts = TransactionMonitoringService.check_batch_patterns(account)
            alerts_created += len(alerts)
            accounts_checked += 1
        except Exception as e:
            logger.error(
                f"[BATCH_MONITORING] Error checking account {account.uuid}: {str(e)}",
                exc_info=True,
            )

    logger.info(f"[BATCH_MONITORING] Checked {accounts_checked} accounts, created {alerts_created} new alerts")
    return f"Checked {accounts_checked} accounts, created {alerts_created} alerts"


@app.periodic(cron="0 4 * * *")
@app.task(
    name="compliance.tasks.check_periodic_reviews",
    retry=RetryStrategy(max_attempts=4, wait=60),
)
def check_periodic_reviews(timestamp: int) -> str:
    """Flag risk assessments due for periodic review. Runs daily at 04:00 UTC."""
    from compliance.constants import ALERT_SEVERITY_MEDIUM, ALERT_TYPE_MANUAL
    from compliance.models import ComplianceAlert, CustomerRiskAssessment

    due_for_review = CustomerRiskAssessment.objects.due_for_review()

    flagged_count = 0
    for assessment in due_for_review:
        existing_alert = ComplianceAlert.objects.filter(
            user_account=assessment.user_account,
            alert_type="periodic_review",
            status__in=["new", "reviewing"],
        ).exists()

        if not existing_alert:
            ComplianceAlert.objects.create(
                user_account=assessment.user_account,
                alert_type=ALERT_TYPE_MANUAL,
                severity=ALERT_SEVERITY_MEDIUM,
                triggered_rule="REVIEW-001",
                description="Periodic risk assessment review required (24-month cycle)",
                alert_data={
                    "assessment_uuid": str(assessment.uuid),
                    "current_rating": assessment.overall_risk_rating,
                    "valid_from": assessment.valid_from.isoformat() if assessment.valid_from else None,
                    "next_review_date": (
                        assessment.next_review_date.isoformat() if assessment.next_review_date else None
                    ),
                },
            )
            flagged_count += 1

    logger.info(f"[PERIODIC_REVIEW] Flagged {flagged_count} assessments for periodic review")
    return f"Flagged {flagged_count} assessments for periodic review"


@app.task(
    name="compliance.tasks.notify_internal-assistant_payslip_uploaded",
    retry=RetryStrategy(max_attempts=6, wait=60),
)
def notify_internal-assistant_payslip_uploaded(document_uuid: str) -> str:
    """Publish a payslip-upload event for internal-assistant to deliver to Slack.

    Mirrors notify_internal-assistant_compliance_alert but for the documents-side
    signal. Idempotency: if the Document already has a slack_thread_ts,
    we skip rather than post a duplicate.
    """
    from compliance.services.internal-assistant_alerts import publish_payslip_uploaded_event
    from documents.models import Document

    if not settings.INTERNAL-ASSISTANT_COMPLIANCE_ALERTS_ENABLED:
        logger.info(
            "[INTERNAL-ASSISTANT_PAYSLIP] Skipping document %s because internal-assistant notifications are disabled",
            document_uuid,
        )
        return "internal-assistant notifications disabled"

    document = Document.objects.get(uuid=document_uuid)
    if document.slack_thread_ts:
        logger.info(
            "[INTERNAL-ASSISTANT_PAYSLIP] Document %s already has Slack thread %s",
            document.uuid,
            document.slack_thread_ts,
        )
        return "Already delivered"

    message_id = publish_payslip_uploaded_event(document)
    return f"Published internal-assistant payslip-uploaded event {message_id}"


@app.task(
    name="compliance.tasks.notify_internal-assistant_compliance_alert",
    retry=RetryStrategy(max_attempts=6, wait=60),
)
def notify_internal-assistant_compliance_alert(alert_uuid: str) -> str:
    """Publish a new compliance alert event for internal-assistant to deliver to Slack."""
    from compliance.models import ComplianceAlert
    from compliance.services.internal-assistant_alerts import (
        publish_compliance_alert_event,
        should_notify_internal-assistant,
    )

    if not settings.INTERNAL-ASSISTANT_COMPLIANCE_ALERTS_ENABLED:
        logger.info("[INTERNAL-ASSISTANT_ALERTS] Skipping alert %s because notifications are disabled", alert_uuid)
        return "internal-assistant compliance alert notifications disabled"

    alert = ComplianceAlert.objects.get(uuid=alert_uuid)
    if alert.slack_thread_ts:
        logger.info("[INTERNAL-ASSISTANT_ALERTS] Alert %s already has Slack thread %s", alert.uuid, alert.slack_thread_ts)
        return "Alert already delivered to Slack"

    if not should_notify_internal-assistant(alert.severity):
        logger.info("[INTERNAL-ASSISTANT_ALERTS] Alert %s severity %s is below notification threshold", alert.uuid, alert.severity)
        return "Alert severity below notification threshold"

    message_id = publish_compliance_alert_event(alert)
    return f"Published internal-assistant compliance alert event {message_id}"
