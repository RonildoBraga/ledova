from django.core.exceptions import PermissionDenied

from companies.models import Company
from documents.models import Document, DocumentRead
from operators.models import DeploymentMode, Operator
from users.models import UserAccount
from users.models.user_account import AccountRole


def documents_enabled():
    mode = Operator.objects.values_list("deployment_mode", flat=True).first()
    return mode in (None, DeploymentMode.REGISTRY)


def require_documents_enabled():
    if not documents_enabled():
        raise PermissionDenied("Supporting payslips are unavailable in this deployment.")


def deployment_mode_error(mode):
    if mode == DeploymentMode.SINGLE_ISSUER and Document.objects.filter(purged_at__isnull=True).exists():
        return "Retained payslips must be removed under their retention policy before switching to single issuer."
    return None


def may_review_documents(user):
    if not user.is_active or not user.is_staff or not user.has_perm("documents.view_document"):
        return False
    if not documents_enabled():
        return False
    if Company.objects.filter(owner=user).exists():
        return False
    return (
        not UserAccount.objects.accounts_the_user_is_a_member_of(user)
        .filter(role__in=[AccountRole.COMPANY, AccountRole.BOTH])
        .exists()
    )


def record_document_read(user, document, kind):
    DocumentRead.objects.create(
        actor_id=user.pk,
        document_uuid=document.pk,
        classification_uuid=document.classification_id,
        kind=kind,
    )
