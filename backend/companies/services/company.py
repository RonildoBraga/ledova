import logging

from django.db import transaction

from companies.exceptions import MissingRequiredDocumentsException
from companies.models import LISTING_REQUIRED_DOCUMENTS, Company, DocumentType
from users.models import UserProfile
from users.tasks.notifications import send_push_notification

logger = logging.getLogger(__name__)


APPLICANT_NOTIFICATIONS = {
    "submit": ("Application submitted", "{name} was submitted for review."),
    "resubmit": ("Application resubmitted", "{name} was resubmitted with your response."),
    "start_review": ("Review started", "The review of {name} has started."),
    "request_info": ("More information requested", "More information requested: {reason}"),
    "approve": ("Application approved", "{name} has been approved."),
    "reject": ("Application rejected", "{name} was rejected: {reason}"),
    "activate": ("Company activated", "{name} is now active."),
    "withdraw": ("Application withdrawn", "{name} was withdrawn."),
}


def register_company(owner, name: str, acn: str, primary_contact_data: dict, **kwargs) -> Company:
    company = Company.objects.create(owner=owner, name=name, acn=acn, **kwargs)

    full_name = f"{primary_contact_data['first_name']} {primary_contact_data['last_name']}".strip()
    UserProfile.objects.update_or_create(user=owner, defaults={"full_name": full_name})

    logger.info(f"Registered new company: {company.name} (ACN: {acn})")
    return company


@transaction.atomic
def transition_company(company: Company, method: str, **kwargs) -> Company:
    getattr(company, method)(**kwargs)
    message = APPLICANT_NOTIFICATIONS.get(method)
    if message:
        title, body = message
        send_push_notification.defer(
            user_id=str(company.owner_id),
            title=title,
            body=body.format(name=company.name, reason=kwargs.get("reason", "")),
            data={"type": "company", "event": method, "company_id": str(company.uuid), "status": company.status},
            notification_type="general",
        )
    return company


@transaction.atomic
def submit_application(company: Company, submitted_by) -> Company:
    uploaded_types = set(company.documents.values_list("document_type", flat=True))
    missing_types = {dt.value for dt in LISTING_REQUIRED_DOCUMENTS} - uploaded_types
    if missing_types:
        raise MissingRequiredDocumentsException(sorted(DocumentType(t).label for t in missing_types))

    transition_company(company, "submit", submitted_by=submitted_by)
    logger.info(f"Application submitted: {company.name} by {submitted_by.email}")
    return company
