from django.utils import timezone

from companies.identity import company_identity, registered_name
from companies.models import Company, CompanyRegistryCheck, RegistryCheckStatus
from companies.validators import digits_of
from integrations.abr import lookup_company
from shared.db import atomic


def begin_registry_check(company, purpose, initiated_by):
    check = CompanyRegistryCheck.objects.create(
        company=company,
        initiated_by=initiated_by,
        purpose=purpose,
        requested_name=company.name,
        requested_acn=company.acn,
        requested_abn=company.abn,
        identity=company_identity(company),
        lifecycle_revision=company.lifecycle_revision,
    )
    company.registry_check = check
    company.registry_status = RegistryCheckStatus.PENDING
    company.registry_reason = "checking"
    company.registry_checked_at = None
    company.registry_entity_name = ""
    company.registry_entity_status = ""
    company.registry_identity = check.identity
    company.registry_revision = check.lifecycle_revision
    company.registry_purpose = purpose
    company.save(update_fields=REGISTRY_FIELDS)
    return check


REGISTRY_FIELDS = (
    "registry_check",
    "registry_status",
    "registry_reason",
    "registry_checked_at",
    "registry_entity_name",
    "registry_entity_status",
    "registry_identity",
    "registry_revision",
    "registry_purpose",
    "updated_at",
)


def observation_result(check, observation):
    if observation.reason:
        status = RegistryCheckStatus.FAILED if observation.reason == "not_found" else RegistryCheckStatus.PENDING
        return status, observation.reason
    if not all((observation.abn, observation.acn, observation.entity_name, observation.entity_status)):
        return RegistryCheckStatus.PENDING, "incomplete_identity"
    if (
        digits_of(observation.acn) != check.identity["acn"]
        or check.identity["abn"]
        and digits_of(observation.abn) != check.identity["abn"]
    ):
        return RegistryCheckStatus.FAILED, "identifier_mismatch"
    if observation.entity_status.casefold() == "cancelled":
        return RegistryCheckStatus.FAILED, "cancelled"
    if observation.entity_status.casefold() != "active":
        return RegistryCheckStatus.PENDING, "unknown_status"
    if registered_name(observation.entity_name) != check.identity["name"]:
        return RegistryCheckStatus.FAILED, "name_mismatch"
    return RegistryCheckStatus.PASSED, "matched"


def complete_registry_check(check, observation):
    with atomic(durable=True):
        company = Company.objects.select_for_update().get(pk=check.company_id)
        check = CompanyRegistryCheck.objects.select_for_update().get(pk=check.pk)
        if check.completed_at is not None:
            return check
        check.status, check.reason = observation_result(check, observation)
        check.completed_at = timezone.now()
        check.registry_abn = observation.abn
        check.registry_acn = observation.acn
        for field in (
            "entity_name",
            "entity_type",
            "entity_status",
            "effective_from",
            "retrieved_at",
            "register_updated_at",
        ):
            setattr(check, field, getattr(observation, field))
        check.save()
        if (
            company.registry_check_id == check.pk
            and company.lifecycle_revision == check.lifecycle_revision
            and company_identity(company) == check.identity
        ):
            company.registry_status = check.status
            company.registry_reason = check.reason
            company.registry_checked_at = check.completed_at
            company.registry_entity_name = check.entity_name
            company.registry_entity_status = check.entity_status
            company.save(update_fields=REGISTRY_FIELDS)
        return check


def perform_registry_check(check):
    observation = lookup_company(acn=check.identity["acn"], abn=check.identity["abn"])
    return complete_registry_check(check, observation)
