from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from users.models import (
    InvestorCategory,
    InvestorClassification,
    InvestorClassificationStatus,
    UserAccount,
    UserProfile,
)

User = get_user_model()
PASSWORD = "pw-12345678"


def make_investor(label, *, account_status="active", id_verified=True, staff=False, role="investor"):
    user = User.objects.create_user(
        email=f"{label}@investors.example.test",
        password=PASSWORD,
        is_staff=staff,
        is_active=True,
        is_email_verified=True,
    )
    profile = UserProfile.objects.create(user=user, full_name=f"{label} holder", is_id_verified=id_verified)
    account = UserAccount.objects.create(
        account_number=f"ACC-{label.upper()}"[:20], account_status=account_status, role=role, director=profile
    )
    account.user_profiles.add(profile)
    return user, account


def make_classification(account, **overrides):
    fields = {
        "user_account": account,
        "category": InvestorCategory.PROFESSIONAL_INVESTOR,
        "declaration_accepted": True,
        "declaration_text": "Declared",
        "declared_basis": "Basis",
        "evidence_file_size": 12,
        "evidence_mime_type": "application/pdf",
        "submitted_at": timezone.now(),
    }
    fields.update(overrides)
    classification = InvestorClassification.objects.create(**fields)
    return classification


def attach_evidence(classification, payload=b"evidence bytes"):
    classification.evidence_file.save(f"{classification.uuid}.pdf", ContentFile(payload), save=True)
    return classification


def verified_classification(account, reviewer, **overrides):
    expires_at = overrides.pop("expires_at", timezone.now() + timezone.timedelta(days=365))
    classification = make_classification(account, **overrides)
    classification.verify(reviewed_by=reviewer, expires_at=expires_at)
    classification.refresh_from_db()
    return classification


def revoked_classification(account, reviewer, **overrides):
    classification = verified_classification(account, reviewer, **overrides)
    classification.revoke(reviewed_by=reviewer, reason="No longer holds")
    classification.refresh_from_db()
    return classification


def rejected_classification(account, reviewer, **overrides):
    classification = make_classification(account, **overrides)
    classification.reject(reviewed_by=reviewer, reason="Evidence insufficient")
    classification.refresh_from_db()
    return classification


SUBMITTED = InvestorClassificationStatus.SUBMITTED
