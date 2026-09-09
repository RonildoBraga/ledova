import logging

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from companies.exceptions import (
    CompanyHoldsARegisterException,
    CompanyHoldsShareClassesException,
    MissingRequiredDocumentsException,
    OfficeholderAttestationRequiredException,
    RegistryVerificationRequiredException,
)
from companies.identity import officeholder_declaration
from companies.models import (
    LISTING_REQUIRED_DOCUMENTS,
    Company,
    CompanyStatus,
    DocumentType,
    RegistryCheckPurpose,
)
from companies.services.registry import begin_registry_check, perform_registry_check
from shared.constants import normalize_chain
from shared.db import atomic
from users.models import UserProfile
from users.tasks.notifications import send_push_notification
from wallets.models import Wallet
from wallets.models.wallet import Blockchain

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


def primary_wallet_for(company: Company, chain: str | None = None):
    chain = normalize_chain(chain or Blockchain.BASE.value)
    if company.operator_wallet:
        return company.operator_wallet if company.operator_wallet.chain == chain else None

    return Wallet.objects.visible_to_user(company.owner).verified_for_chain(chain)


def register_company(owner, name: str, acn: str, primary_contact_data: dict, **kwargs) -> Company:
    company = Company.objects.create(owner=owner, name=name, acn=acn, **kwargs)

    full_name = f"{primary_contact_data['first_name']} {primary_contact_data['last_name']}".strip()
    UserProfile.objects.update_or_create(user=owner, defaults={"full_name": full_name})

    logger.info(f"Registered new company: {company.name} (ACN: {acn})")
    return company


def _notify_transition(company, method, **kwargs):
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


def _attest_officeholder(company, actor, declaration):
    if (
        declaration.get("attest_officeholder") is not True
        or not declaration.get("declarant_name", "").strip()
        or not declaration.get("board_resolution_reference", "").strip()
    ):
        raise OfficeholderAttestationRequiredException()
    company.declarant_name = declaration["declarant_name"].strip()
    company.board_resolution_reference = declaration["board_resolution_reference"].strip()
    if len(company.declarant_name) > 255 or len(company.board_resolution_reference) > 255:
        raise OfficeholderAttestationRequiredException()
    company.officeholder_attested_by = actor
    company.officeholder_attested_at = timezone.now()
    company.officeholder_attestation = officeholder_declaration(company)
    company.lifecycle_revision += 1
    company.save(
        update_fields=[
            "declarant_name",
            "board_resolution_reference",
            "officeholder_attested_by",
            "officeholder_attested_at",
            "officeholder_attestation",
            "lifecycle_revision",
            "updated_at",
        ]
    )


ACTIVE_METHODS = {
    CompanyStatus.APPROVED: "activate",
    CompanyStatus.WARNING: "resolve_warning",
    CompanyStatus.SUSPENDED: "reinstate",
}


def _registry_transition(company, method, actor, declaration):
    with atomic(durable=True):
        current = Company.objects.select_for_update().get(pk=company.pk)
        if method == "start_review":
            current.start_review()
            _notify_transition(current, method)
            purpose = RegistryCheckPurpose.REVIEW
        elif method == "retry_registry":
            current._require_status(
                [
                    CompanyStatus.REVIEW,
                    CompanyStatus.APPROVED,
                    CompanyStatus.ACTIVE,
                    CompanyStatus.WARNING,
                    CompanyStatus.SUSPENDED,
                ],
                CompanyStatus.REVIEW,
            )
            purpose = RegistryCheckPurpose.RETRY
        else:
            allowed = [state for state, transition in ACTIVE_METHODS.items() if method in (transition, "set_active")]
            current._require_status(allowed, CompanyStatus.ACTIVE)
            method = ACTIVE_METHODS[current.status]
            if declaration:
                _attest_officeholder(current, actor, declaration)
            current._require_attestation()
            purpose = RegistryCheckPurpose.ACTIVATION
        check = begin_registry_check(current, purpose, actor)
    check = perform_registry_check(check)
    if purpose != RegistryCheckPurpose.ACTIVATION:
        return Company.objects.get(pk=company.pk)
    with atomic(durable=True):
        current = Company.objects.select_for_update().get(pk=company.pk)
        if current.registry_check_id != check.pk:
            raise RegistryVerificationRequiredException()
        getattr(current, method)()
        _notify_transition(current, method)
    return current


def transition_company(company: Company, method: str, *, actor=None, declaration=None, **kwargs) -> Company:
    actor = actor or kwargs.get("approved_by") or kwargs.get("rejected_by")
    registry_methods = {"start_review", "retry_registry", "set_active", *ACTIVE_METHODS.values()}
    if method in registry_methods | {"approve"}:
        if actor is None or not actor.is_staff:
            raise PermissionDenied("An operator must perform the company review.")
    if method in registry_methods:
        return _registry_transition(company, method, actor, declaration)
    with atomic():
        current = Company.objects.select_for_update().get(pk=company.pk)
        if method == "approve":
            current._require_status([CompanyStatus.REVIEW], CompanyStatus.APPROVED)
            _attest_officeholder(current, actor, declaration or {})
            kwargs["approved_by"] = actor
        getattr(current, method)(**kwargs)
        _notify_transition(current, method, **kwargs)
    return current


@atomic()
def submit_application(company: Company, submitted_by) -> Company:
    uploaded_types = set(company.documents.values_list("document_type", flat=True))
    missing_types = {dt.value for dt in LISTING_REQUIRED_DOCUMENTS} - uploaded_types
    if missing_types:
        raise MissingRequiredDocumentsException(sorted(DocumentType(t).label for t in missing_types))

    company = transition_company(company, "submit", submitted_by=submitted_by)
    logger.info(f"Application submitted: {company.uuid} ({company.name}) by user {submitted_by.pk}")
    return company


def delete_company(company: Company) -> None:
    on_chain = company.tokens.on_chain().count()
    if on_chain:
        logger.warning(f"Refused to delete {company.name}: {on_chain} on-chain share class(es) hold its register")
        raise CompanyHoldsARegisterException(on_chain)

    share_classes = company.tokens.count()
    if share_classes:
        logger.warning(f"Refused to delete {company.name}: {share_classes} share class(es) are still attached")
        raise CompanyHoldsShareClassesException(share_classes)

    logger.info(f"Deleting company: {company.name} (ACN: {company.acn})")
    company.delete()
