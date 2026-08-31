import logging
from datetime import timedelta
from typing import Any, Dict

from django.utils import timezone

from ledova_backend.procrastinate_app import app
from companies.models import Company, CompanyStatus
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


@app.task
def send_application_status_notification(company_uuid: str, new_status: str) -> Dict[str, Any]:
    try:
        company = Company.objects.get(uuid=company_uuid)
    except Company.DoesNotExist:
        logger.error(f"{LoggingContext.COMPANY} Company not found: {company_uuid}")
        return {"status": "error", "reason": "company_not_found"}

    if not company.owner:
        logger.warning(f"{LoggingContext.COMPANY} No owner for {company.name}, skipping notification")
        return {"status": "skipped", "reason": "no_owner"}

    logger.info(
        f"{LoggingContext.COMPANY} Would send status notification to "
        f"{company.email} for {company.name}: {new_status}"
    )

    return {
        "status": "success",
        "company": company.name,
        "recipient": company.email,
        "new_status": new_status,
    }


@app.task
def send_review_reminder(days_pending: int = 7) -> Dict[str, Any]:
    cutoff_date = timezone.now() - timedelta(days=days_pending)

    pending_companies = Company.objects.filter(
        status__in=[CompanyStatus.SUBMITTED, CompanyStatus.REVIEW],
        submitted_at__lt=cutoff_date,
    )

    reminder_count = 0
    for company in pending_companies:
        logger.info(
            f"{LoggingContext.COMPANY_REVIEW} Would send review reminder for "
            f"{company.name} (pending since {company.submitted_at})"
        )
        reminder_count += 1

    logger.info(f"{LoggingContext.TASK} Review reminder task completed - Sent {reminder_count} reminders")
    return {"status": "success", "reminders_sent": reminder_count}
