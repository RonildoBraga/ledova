import logging
from typing import Optional

from django.db import transaction

from companies.exceptions import (
    CompanyAlreadyExistsException,
    CompanyNotApprovedException,
    CompanyNotFoundException,
    InvalidStatusTransitionException,
    MissingRequiredDocumentsException,
)
from companies.models import Company, CompanyStatus
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


class CompanyService:
    @staticmethod
    def register_company(
        owner,
        name: str,
        acn: str,
        primary_contact_data: dict,
        **kwargs,
    ) -> Company:
        from users.models import UserProfile

        if Company.objects.filter(acn=acn).exists():
            logger.warning(f"{LoggingContext.COMPANY_REGISTRATION} Registration attempt with existing ACN: {acn}")
            raise CompanyAlreadyExistsException()

        company = Company.objects.create(
            owner=owner,
            name=name,
            acn=acn,
            **kwargs,
        )

        UserProfile.objects.update_or_create(
            user=owner,
            defaults=primary_contact_data,
        )

        logger.info(f"{LoggingContext.COMPANY_REGISTRATION} Registered new company: {company.name} (ACN: {acn})")
        return company

    @staticmethod
    def get_company_by_uuid(uuid: str) -> Company:
        try:
            return Company.objects.get(uuid=uuid)
        except Company.DoesNotExist:
            raise CompanyNotFoundException()

    @staticmethod
    def get_company_by_acn(acn: str) -> Company:
        try:
            return Company.objects.get(acn=acn)
        except Company.DoesNotExist:
            raise CompanyNotFoundException()

    @staticmethod
    @transaction.atomic
    def submit_application(company: Company, submitted_by) -> Company:
        if company.status != CompanyStatus.DRAFT:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Submitted",
            )

        from companies.models import LISTING_REQUIRED_DOCUMENTS, DocumentType

        uploaded_types = set(company.documents.values_list("document_type", flat=True))
        required_types = set(dt.value for dt in LISTING_REQUIRED_DOCUMENTS)
        missing_types = required_types - uploaded_types

        if missing_types:
            missing_names = [dict(DocumentType.choices).get(t, t) for t in missing_types]
            raise MissingRequiredDocumentsException(missing_names)

        company.submit(submitted_by=submitted_by)
        logger.info(
            f"{LoggingContext.COMPANY_SUBMISSION} Application submitted: {company.name} by {submitted_by.email}"
        )
        return company

    @staticmethod
    @transaction.atomic
    def resubmit_application(company: Company, response: str) -> Company:
        if company.status != CompanyStatus.INFO_REQUIRED:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Submitted",
            )

        company.resubmit(response=response)
        logger.info(f"{LoggingContext.COMPANY_SUBMISSION} Application resubmitted: {company.name}")
        return company

    @staticmethod
    @transaction.atomic
    def withdraw_application(company: Company, reason: Optional[str] = None) -> Company:
        if company.status not in [
            CompanyStatus.DRAFT,
            CompanyStatus.SUBMITTED,
            CompanyStatus.INFO_REQUIRED,
        ]:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Withdrawn",
            )

        company.withdraw(reason=reason)
        logger.info(f"{LoggingContext.COMPANY_SUBMISSION} Application withdrawn: {company.name}")
        return company

    @staticmethod
    @transaction.atomic
    def start_review(company: Company, reviewer) -> Company:
        if company.status != CompanyStatus.SUBMITTED:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Under Review",
            )

        company.start_review(reviewer=reviewer)
        logger.info(f"{LoggingContext.COMPANY_REVIEW} Review started: {company.name} by {reviewer.email}")
        return company

    @staticmethod
    @transaction.atomic
    def request_info(company: Company, reason: str, requested_by) -> Company:
        if company.status != CompanyStatus.REVIEW:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Additional Information Required",
            )

        company.request_info(reason=reason)
        logger.info(f"{LoggingContext.COMPANY_REVIEW} Info requested: {company.name} - {reason}")
        return company

    @staticmethod
    @transaction.atomic
    def approve_company(company: Company, approved_by) -> Company:
        if company.status != CompanyStatus.REVIEW:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Approved",
            )

        company.approve(approved_by=approved_by)
        logger.info(f"{LoggingContext.COMPANY_APPROVAL} Application approved: {company.name} by {approved_by.email}")
        return company

    @staticmethod
    @transaction.atomic
    def reject_company(company: Company, reason: str, rejected_by) -> Company:
        if company.status not in [CompanyStatus.SUBMITTED, CompanyStatus.REVIEW]:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Rejected",
            )

        company.reject(reason=reason, rejected_by=rejected_by)
        logger.info(f"{LoggingContext.COMPANY_REVIEW} Application rejected: {company.name} - {reason}")
        return company

    @staticmethod
    @transaction.atomic
    def activate_company(company: Company) -> Company:
        if company.status != CompanyStatus.APPROVED:
            raise CompanyNotApprovedException()

        company.activate()
        logger.info(f"{LoggingContext.COMPANY_ACTIVATION} Company activated: {company.name}")
        return company

    @staticmethod
    @transaction.atomic
    def issue_warning(company: Company, reason: str, issued_by) -> Company:
        if company.status != CompanyStatus.ACTIVE:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Compliance Warning",
            )

        company.issue_warning(reason=reason)
        logger.info(f"{LoggingContext.COMPANY} Warning issued: {company.name} - {reason}")
        return company

    @staticmethod
    @transaction.atomic
    def resolve_warning(company: Company) -> Company:
        if company.status != CompanyStatus.WARNING:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Active",
            )

        company.resolve_warning()
        logger.info(f"{LoggingContext.COMPANY} Warning resolved: {company.name}")
        return company

    @staticmethod
    @transaction.atomic
    def suspend_company(company: Company, reason: str, suspended_by) -> Company:
        if company.status not in [CompanyStatus.ACTIVE, CompanyStatus.WARNING]:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Suspended",
            )

        company.suspend(reason=reason)
        logger.info(f"{LoggingContext.COMPANY_SUSPENSION} Company suspended: {company.name} - {reason}")
        return company

    @staticmethod
    @transaction.atomic
    def reinstate_company(company: Company) -> Company:
        if company.status != CompanyStatus.SUSPENDED:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Active",
            )

        company.reinstate()
        logger.info(f"{LoggingContext.COMPANY} Company reinstated: {company.name}")
        return company

    @staticmethod
    @transaction.atomic
    def delist_company(company: Company, reason: str, delisted_by) -> Company:
        if company.status in [CompanyStatus.DRAFT, CompanyStatus.REJECTED, CompanyStatus.WITHDRAWN]:
            raise InvalidStatusTransitionException(
                from_status=company.get_status_display(),
                to_status="Delisted",
            )

        company.delist(reason=reason)
        logger.info(f"{LoggingContext.COMPANY_DELISTING} Company delisted: {company.name} - {reason}")
        return company
