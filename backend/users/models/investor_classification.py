import os
import uuid as uuid_lib
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel
from users.exceptions import InvalidClassificationTransitionException
from users.querysets.investor_classification import InvestorClassificationQuerySet

PRODUCT_VALUE_THRESHOLD_AUD = Decimal("500000.00")
CERTIFICATE_VALIDITY_YEARS = 2


def investor_evidence_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    unique_name = f"{uuid_lib.uuid4()}{ext}"
    return f"users/{instance.user_account.uuid}/investor-classifications/{instance.category}/{unique_name}"


def plus_years(value, years=CERTIFICATE_VALIDITY_YEARS):
    if isinstance(value, datetime):
        moment = value
    else:
        moment = timezone.make_aware(datetime.combine(value, time.min), timezone.get_default_timezone())
    try:
        return moment.replace(year=moment.year + years)
    except ValueError:
        return moment.replace(year=moment.year + years, day=28)


class InvestorCategory(models.TextChoices):
    PRODUCT_VALUE = "product_value", "Product value of at least AUD 500,000 (s708(8)(a))"
    ACCOUNTANT_CERTIFICATE = "accountant_certificate", "Qualified accountant's certificate (s708(8)(c))"
    PROFESSIONAL_INVESTOR = "professional_investor", "Professional investor (s708(11) / s761G(7)(d))"
    ASSOCIATED_PERSON = "associated_person", "Person associated with the issuer (s708(12))"


class InvestorClassificationStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"
    REVOKED = "revoked", "Revoked"


class CertifierBody(models.TextChoices):
    CA_ANZ = "ca_anz", "Chartered Accountants Australia and New Zealand"
    CPA_AUSTRALIA = "cpa_australia", "CPA Australia"
    IPA = "ipa", "Institute of Public Accountants"


DECLARATION_TEXT = {
    InvestorCategory.PRODUCT_VALUE: (
        "I declare that the amount payable on acceptance of this offer is at least AUD 500,000, so the offer is "
        "made to me under section 708(8)(a) of the Corporations Act 2001 (Cth) and no disclosure document is "
        "required."
    ),
    InvestorCategory.ACCOUNTANT_CERTIFICATE: (
        "I declare that a qualified accountant has certified, within the last two years, that I have net assets of "
        "at least AUD 2.5 million or gross income of at least AUD 250,000 for each of the last two financial "
        "years, so the offer is made to me under section 708(8)(c) of the Corporations Act 2001 (Cth)."
    ),
    InvestorCategory.PROFESSIONAL_INVESTOR: (
        "I declare that I am a professional investor within the meaning of section 708(11) and section 761G(7)(d) "
        "of the Corporations Act 2001 (Cth)."
    ),
    InvestorCategory.ASSOCIATED_PERSON: (
        "I declare that I am a person associated with the named issuer within the meaning of section 708(12) of "
        "the Corporations Act 2001 (Cth)."
    ),
}


ASSOCIATED_PERSON_SCOPE_ERROR = (
    "An associated person claim must name the issuer it is scoped to, and no other category may name one."
)


class InvestorClassification(BaseModel):

    objects = InvestorClassificationQuerySet.as_manager()

    user_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.CASCADE,
        related_name="investor_classifications",
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="investor_classifications",
        help_text="Set only for an associated person; empty means the claim applies to every offering.",
    )
    category = models.CharField(max_length=30, choices=InvestorCategory.choices)
    status = models.CharField(
        max_length=20,
        choices=InvestorClassificationStatus.choices,
        default=InvestorClassificationStatus.SUBMITTED,
    )

    declaration_accepted = models.BooleanField(default=False)
    declaration_text = models.TextField(blank=True)
    declared_basis = models.TextField(blank=True)

    evidence_file = models.FileField(upload_to=investor_evidence_path, max_length=255, null=True, blank=True)
    evidence_file_size = models.PositiveIntegerField(null=True, blank=True)
    evidence_mime_type = models.CharField(max_length=100, blank=True)

    certificate_issued_at = models.DateField(null=True, blank=True)
    certifier_name = models.CharField(max_length=255, blank=True)
    certifier_body = models.CharField(max_length=20, choices=CertifierBody.choices, blank=True)
    certifier_membership_number = models.CharField(max_length=50, blank=True)

    submitted_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_investor_classifications",
        help_text="Staff member who reviewed the claim",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "Investor Classification"
        verbose_name_plural = "Investor Classifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user_account", "status"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user_account"],
                condition=models.Q(status=InvestorClassificationStatus.SUBMITTED),
                name="investor_classification_one_open_submission",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    category=InvestorCategory.ASSOCIATED_PERSON,
                    company__isnull=False,
                )
                | ~models.Q(category=InvestorCategory.ASSOCIATED_PERSON) & models.Q(company__isnull=True),
                name="investor_classification_associated_person_names_the_issuer",
                violation_error_message=ASSOCIATED_PERSON_SCOPE_ERROR,
            ),
        ]

    def __str__(self):
        return f"{self.get_category_display()} for {self.user_account_id}"

    @property
    def is_live(self):
        if self.status != InvestorClassificationStatus.VERIFIED:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    @property
    def is_expired(self):
        return self.status == InvestorClassificationStatus.VERIFIED and not self.is_live

    @property
    def default_expiry(self):
        return plus_years(self.certificate_issued_at or timezone.now())

    def _require_status(self, allowed, to_status):
        if self.status not in allowed:
            raise InvalidClassificationTransitionException(
                from_status=self.get_status_display(), to_status=to_status.label
            )

    def verify(self, reviewed_by, expires_at, notes=""):
        self._require_status([InvestorClassificationStatus.SUBMITTED], InvestorClassificationStatus.VERIFIED)
        self.status = InvestorClassificationStatus.VERIFIED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.expires_at = expires_at
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "expires_at", "updated_at"])

    def reject(self, reviewed_by, reason):
        self._require_status([InvestorClassificationStatus.SUBMITTED], InvestorClassificationStatus.REJECTED)
        self.status = InvestorClassificationStatus.REJECTED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    def revoke(self, reviewed_by, reason):
        self._require_status([InvestorClassificationStatus.VERIFIED], InvestorClassificationStatus.REVOKED)
        self.status = InvestorClassificationStatus.REVOKED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])
