import logging

from django.db import transaction

from companies.exceptions import MissingRequiredDocumentsException
from companies.models import LISTING_REQUIRED_DOCUMENTS, Company, DocumentType
from shared.utils.logging_utils import LoggingContext
from users.models import UserProfile

logger = logging.getLogger(__name__)


def register_company(owner, name: str, acn: str, primary_contact_data: dict, **kwargs) -> Company:
    company = Company.objects.create(owner=owner, name=name, acn=acn, **kwargs)

    # primary_contact_data['phone'] is the owner's own profile phone echoed back by the
    # clients as "<country_code> <number>", so it is deliberately not written to the profile.
    full_name = f"{primary_contact_data['first_name']} {primary_contact_data['last_name']}".strip()
    UserProfile.objects.update_or_create(user=owner, defaults={"full_name": full_name})

    logger.info(f"{LoggingContext.COMPANY_REGISTRATION} Registered new company: {company.name} (ACN: {acn})")
    return company


@transaction.atomic
def submit_application(company: Company, submitted_by) -> Company:
    uploaded_types = set(company.documents.values_list("document_type", flat=True))
    missing_types = {dt.value for dt in LISTING_REQUIRED_DOCUMENTS} - uploaded_types
    if missing_types:
        raise MissingRequiredDocumentsException(sorted(DocumentType(t).label for t in missing_types))

    company.submit(submitted_by=submitted_by)
    logger.info(f"{LoggingContext.COMPANY} Application submitted: {company.name} by {submitted_by.email}")
    return company
