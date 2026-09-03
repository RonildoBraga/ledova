"""Background tasks for compliance (AML/CTF).

- run_batch_monitoring: hourly pattern-rule sweep over recent transactions.
- check_periodic_reviews: daily flag of risk assessments overdue for 24-month review.
"""

import logging
from datetime import timedelta

from django.utils import timezone
from procrastinate import RetryStrategy

from compliance.constants import (
    ALERT_SEVERITY_MEDIUM,
    ALERT_STATUS_NEW,
    ALERT_STATUS_REVIEWING,
    ALERT_TYPE_PERIODIC_REVIEW,
    ASSESSMENT_STATUS_COMPLETE,
    BATCH_MONITORING_LOOKBACK_HOURS,
)
from ledova_backend.procrastinate_app import app

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
    from wallets.models import Transaction

    if not MonitoringRule.objects.active().pattern_rules().exists():
        logger.info("[BATCH_MONITORING] No active pattern rules to check")
        return "No active pattern rules"

    recent = timezone.now() - timedelta(hours=BATCH_MONITORING_LOOKBACK_HOURS)
    active_account_uuids = (
        Transaction.objects.filter(created_at__gte=recent).values_list("wallet__user_account", flat=True).distinct()
    )

    alerts_created = accounts_checked = 0
    for account in UserAccount.objects.filter(uuid__in=active_account_uuids):
        try:
            alerts_created += len(TransactionMonitoringService.check_batch_patterns(account))
            accounts_checked += 1
        except Exception as e:
            logger.error(f"[BATCH_MONITORING] Error checking account {account.uuid}: {e}", exc_info=True)

    logger.info(f"[BATCH_MONITORING] Checked {accounts_checked} accounts, created {alerts_created} new alerts")
    return f"Checked {accounts_checked} accounts, created {alerts_created} alerts"


@app.periodic(cron="0 4 * * *")
@app.task(
    name="compliance.tasks.check_periodic_reviews",
    retry=RetryStrategy(max_attempts=4, wait=60),
)
def check_periodic_reviews(timestamp: int) -> str:
    """Raise one open periodic-review alert per assessment whose review date has passed. Runs daily at 04:00 UTC."""
    from compliance.models import ComplianceAlert, CustomerRiskAssessment

    due_for_review = CustomerRiskAssessment.objects.filter(
        assessment_status=ASSESSMENT_STATUS_COMPLETE, next_review_date__lte=timezone.now()
    )

    flagged_count = 0
    for assessment in due_for_review:
        already_open = ComplianceAlert.objects.filter(
            user_account=assessment.user_account,
            alert_type=ALERT_TYPE_PERIODIC_REVIEW,
            status__in=[ALERT_STATUS_NEW, ALERT_STATUS_REVIEWING],
        ).exists()
        if already_open:
            continue
        ComplianceAlert.objects.create(
            user_account=assessment.user_account,
            alert_type=ALERT_TYPE_PERIODIC_REVIEW,
            severity=ALERT_SEVERITY_MEDIUM,
            triggered_rule="REVIEW-001",
            description="Periodic risk assessment review required (24-month cycle)",
            alert_data={
                "assessment_uuid": str(assessment.uuid),
                "current_rating": assessment.overall_risk_rating,
                "valid_from": assessment.valid_from.isoformat() if assessment.valid_from else None,
                "next_review_date": assessment.next_review_date.isoformat() if assessment.next_review_date else None,
            },
        )
        flagged_count += 1

    logger.info(f"[PERIODIC_REVIEW] Flagged {flagged_count} assessments for periodic review")
    return f"Flagged {flagged_count} assessments for periodic review"
