import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from companies.exceptions import InvalidStatusTransitionException
from companies.querysets.company import CompanyQuerySet
from shared.models import BaseModel
from users.models import UserProfile
from wallets.models import Wallet
from wallets.models.wallet import Blockchain


class CompanyStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted for Review"
    REVIEW = "review", "Under Review"
    INFO_REQUIRED = "info_required", "Additional Information Required"
    APPROVED = "approved", "Approved"

    ACTIVE = "active", "Active"
    WARNING = "warning", "Compliance Warning"
    SUSPENDED = "suspended", "Suspended"
    DELISTED = "delisted", "Delisted"

    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


class CompanyType(models.TextChoices):
    PROPRIETARY = "pty", "Proprietary Limited (Pty Ltd)"
    PUBLIC = "public", "Public Company (Ltd)"
    UNLISTED_PUBLIC = "unlisted", "Unlisted Public Company"


class Company(BaseModel):
    objects = CompanyQuerySet.as_manager()

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
    )

    name = models.CharField(max_length=255)
    trading_name = models.CharField(max_length=255, blank=True)
    company_type = models.CharField(
        max_length=20,
        choices=CompanyType.choices,
        default=CompanyType.PROPRIETARY,
    )

    acn = models.CharField(max_length=11, unique=True)
    abn = models.CharField(max_length=14, blank=True)

    status = models.CharField(
        max_length=20,
        choices=CompanyStatus.choices,
        default=CompanyStatus.DRAFT,
    )

    phone = models.CharField(max_length=20, blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postcode = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=50, default="Australia", blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_company_applications",
    )

    review_started_at = models.DateTimeField(null=True, blank=True)
    review_completed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_companies",
    )

    info_requested_at = models.DateTimeField(null=True, blank=True)
    info_request_reason = models.TextField(blank=True)

    rejection_reason = models.TextField(blank=True)
    rejection_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_companies",
    )

    warning_issued_at = models.DateTimeField(null=True, blank=True)
    warning_reason = models.TextField(blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)
    delisted_at = models.DateTimeField(null=True, blank=True)
    delisting_reason = models.TextField(blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)

    activated_at = models.DateTimeField(null=True, blank=True)

    api_key = models.CharField(max_length=64, unique=True, blank=True)
    api_key_created_at = models.DateTimeField(null=True, blank=True)

    operator_wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operated_companies",
        help_text="The wallet used for signing token operations",
    )

    description = models.TextField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    founded_year = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.acn})"

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = self._generate_api_key()
            self.api_key_created_at = timezone.now()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_api_key():
        return f"ledova_{secrets.token_hex(28)}"

    def regenerate_api_key(self):
        self.api_key = self._generate_api_key()
        self.api_key_created_at = timezone.now()
        self.save(update_fields=["api_key", "api_key_created_at", "updated_at"])
        return self.api_key

    def _require_status(self, allowed, to_status):
        if self.status not in allowed:
            raise InvalidStatusTransitionException(from_status=self.get_status_display(), to_status=to_status.label)

    def submit(self, submitted_by=None):
        self._require_status([CompanyStatus.DRAFT], CompanyStatus.SUBMITTED)
        self.status = CompanyStatus.SUBMITTED
        self.submitted_at = timezone.now()
        self.submitted_by = submitted_by
        self.save(update_fields=["status", "submitted_at", "submitted_by", "updated_at"])

    def start_review(self):
        self._require_status([CompanyStatus.SUBMITTED], CompanyStatus.REVIEW)
        self.status = CompanyStatus.REVIEW
        self.review_started_at = timezone.now()
        self.save(update_fields=["status", "review_started_at", "updated_at"])

    def request_info(self, reason: str):
        self._require_status([CompanyStatus.REVIEW], CompanyStatus.INFO_REQUIRED)
        self.status = CompanyStatus.INFO_REQUIRED
        self.info_requested_at = timezone.now()
        self.info_request_reason = reason
        self.save(update_fields=["status", "info_requested_at", "info_request_reason", "updated_at"])

    def resubmit(self):
        self._require_status([CompanyStatus.INFO_REQUIRED], CompanyStatus.SUBMITTED)
        self.status = CompanyStatus.SUBMITTED
        self.submitted_at = timezone.now()
        self.info_request_reason = ""
        self.save(update_fields=["status", "submitted_at", "info_request_reason", "updated_at"])

    def approve(self, approved_by=None):
        self._require_status([CompanyStatus.REVIEW], CompanyStatus.APPROVED)
        self.status = CompanyStatus.APPROVED
        self.review_completed_at = self.approved_at = timezone.now()
        self.approved_by = approved_by
        self.save(update_fields=["status", "review_completed_at", "approved_at", "approved_by", "updated_at"])

    def activate(self):
        self._require_status([CompanyStatus.APPROVED], CompanyStatus.ACTIVE)
        self.status = CompanyStatus.ACTIVE
        self.activated_at = timezone.now()
        self.save(update_fields=["status", "activated_at", "updated_at"])

    def reject(self, reason: str, rejected_by=None):
        self._require_status([CompanyStatus.REVIEW, CompanyStatus.SUBMITTED], CompanyStatus.REJECTED)
        self.status = CompanyStatus.REJECTED
        self.rejection_reason = reason
        self.rejection_at = self.review_completed_at = timezone.now()
        self.rejected_by = rejected_by
        self.save(
            update_fields=[
                "status",
                "rejection_reason",
                "rejection_at",
                "rejected_by",
                "review_completed_at",
                "updated_at",
            ]
        )

    def withdraw(self, reason: str = ""):
        pending = [CompanyStatus.DRAFT, CompanyStatus.SUBMITTED, CompanyStatus.INFO_REQUIRED]
        self._require_status(pending, CompanyStatus.WITHDRAWN)
        self.status = CompanyStatus.WITHDRAWN
        self.withdrawn_at = timezone.now()
        self.withdrawal_reason = reason
        self.save(update_fields=["status", "withdrawn_at", "withdrawal_reason", "updated_at"])

    def issue_warning(self, reason: str):
        self._require_status([CompanyStatus.ACTIVE], CompanyStatus.WARNING)
        self.status = CompanyStatus.WARNING
        self.warning_issued_at = timezone.now()
        self.warning_reason = reason
        self.save(update_fields=["status", "warning_issued_at", "warning_reason", "updated_at"])

    def resolve_warning(self):
        self._require_status([CompanyStatus.WARNING], CompanyStatus.ACTIVE)
        self.status = CompanyStatus.ACTIVE
        self.save(update_fields=["status", "updated_at"])

    def suspend(self, reason: str = ""):
        self._require_status([CompanyStatus.ACTIVE, CompanyStatus.WARNING], CompanyStatus.SUSPENDED)
        self.status = CompanyStatus.SUSPENDED
        self.suspended_at = timezone.now()
        self.suspension_reason = reason
        self.save(update_fields=["status", "suspended_at", "suspension_reason", "updated_at"])

    def reinstate(self):
        self._require_status([CompanyStatus.SUSPENDED], CompanyStatus.ACTIVE)
        self.status = CompanyStatus.ACTIVE
        self.save(update_fields=["status", "updated_at"])

    def delist(self, reason: str):
        never_active = [CompanyStatus.DRAFT, CompanyStatus.REJECTED, CompanyStatus.WITHDRAWN]
        self._require_status([s for s in CompanyStatus if s not in never_active], CompanyStatus.DELISTED)
        self.status = CompanyStatus.DELISTED
        self.delisted_at = timezone.now()
        self.delisting_reason = reason
        self.save(update_fields=["status", "delisted_at", "delisting_reason", "updated_at"])

    @property
    def is_active(self):
        return self.status == CompanyStatus.ACTIVE

    @property
    def is_approved(self):
        return self.status in [CompanyStatus.APPROVED, CompanyStatus.ACTIVE]

    @property
    def is_pending_review(self):
        return self.status in [
            CompanyStatus.SUBMITTED,
            CompanyStatus.REVIEW,
            CompanyStatus.INFO_REQUIRED,
        ]

    @property
    def can_issue_tokens(self):
        return self.status == CompanyStatus.ACTIVE

    @property
    def display_name(self):
        return self.trading_name or self.name

    @property
    def email(self):
        return self.owner.email

    @property
    def primary_contact(self):
        return getattr(self.owner, "profile", None)

    def get_primary_wallet(self, chain: str | None = None):
        if chain is None:
            chain = Blockchain.BASE.value

        if self.operator_wallet and self.operator_wallet.chain == chain:
            return self.operator_wallet

        profile = UserProfile.objects.filter(user=self.owner).first()
        if not profile:
            return None

        account_ids = profile.user_accounts.values_list("uuid", flat=True)
        return Wallet.objects.filter(user_account_id__in=account_ids).for_chain_with_l2_fallback(chain)
