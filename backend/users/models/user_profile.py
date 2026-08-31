from django.conf import settings
from django.db import models

from integrations.kyc.constants import (
    KYC_PROVIDER_CHOICES,
    PROVIDER_KYCAID,
    REVIEW_GREEN,
    REVIEW_RESULT_CHOICES,
    REVIEW_YELLOW,
    VERIFICATION_STATUS_CHOICES,
)
from shared.models import BaseModel, Country
from users.querysets.user_profile import UserProfileQuerySet


class UserProfile(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    full_name = models.CharField(max_length=100, blank=True, null=True)
    phone_country_code = models.CharField(max_length=5, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    residential_address = models.TextField(blank=True, null=True)

    citizenship_country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL, related_name="citizens"
    )
    residence_country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL, related_name="residents"
    )

    id_document_type = models.CharField(max_length=50, blank=True, null=True)
    id_document_country = models.CharField(max_length=3, blank=True, null=True)

    confirmed_over_18 = models.BooleanField(default=False)
    confirmed_australian_resident = models.BooleanField(default=False)
    confirmed_individual_account = models.BooleanField(default=False)
    pre_screening_completed_at = models.DateTimeField(null=True, blank=True)

    is_id_verified = models.BooleanField(default=False)
    terms_and_conditions = models.BooleanField(default=False)
    is_signup_completed = models.BooleanField(default=False)

    # Provider-agnostic KYC fields
    kyc_provider = models.CharField(
        max_length=20,
        choices=KYC_PROVIDER_CHOICES,
        default=PROVIDER_KYCAID,
    )
    verification_status = models.CharField(
        max_length=50,
        choices=VERIFICATION_STATUS_CHOICES,
        blank=True,
        null=True,
    )
    review_result = models.CharField(
        max_length=20,
        choices=REVIEW_RESULT_CHOICES,
        blank=True,
        null=True,
    )
    rejection_labels = models.JSONField(blank=True, null=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    # KYCAID-specific fields
    kycaid_applicant_id = models.CharField(max_length=100, blank=True, null=True)
    kycaid_verification_id = models.CharField(max_length=100, blank=True, null=True)

    # Sumsub-specific fields
    sumsub_applicant_id = models.CharField(max_length=100, blank=True, null=True)
    sumsub_verification_status = models.CharField(
        max_length=50,
        choices=VERIFICATION_STATUS_CHOICES,
        blank=True,
        null=True,
    )
    sumsub_review_result = models.CharField(
        max_length=50,
        choices=REVIEW_RESULT_CHOICES,
        blank=True,
        null=True,
    )
    sumsub_review_answer = models.CharField(
        max_length=50,
        choices=REVIEW_RESULT_CHOICES,
        blank=True,
        null=True,
    )
    sumsub_rejection_labels = models.JSONField(blank=True, null=True)
    sumsub_verified_at = models.DateTimeField(null=True, blank=True)

    objects = UserProfileQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"UserProfile {self.user.email}"

    @property
    def is_pre_screening_complete(self):
        return self.confirmed_over_18 and self.confirmed_australian_resident and self.confirmed_individual_account

    @property
    def failed_pre_screening_checks(self):
        failed = []
        if not self.confirmed_over_18:
            failed.append("age_confirmation")
        if not self.confirmed_australian_resident:
            failed.append("residency_confirmation")
        if not self.confirmed_individual_account:
            failed.append("individual_account_confirmation")
        return failed

    @property
    def is_verification_approved(self):
        result = self.review_result or self.sumsub_review_result
        return self.is_id_verified and result == REVIEW_GREEN

    @property
    def needs_verification_retry(self):
        result = self.review_result or self.sumsub_review_answer
        return result == REVIEW_YELLOW

    @property
    def active_applicant_id(self):
        if self.kyc_provider == PROVIDER_KYCAID:
            return self.kycaid_applicant_id
        return self.sumsub_applicant_id

    @property
    def used_foreign_passport(self):
        if self.id_document_type and self.id_document_country:
            is_passport = self.id_document_type.upper() in ["PASSPORT", "ID_DOC_PASSPORT"]
            is_foreign = self.id_document_country.upper() != "AU"
            return is_passport and is_foreign
        return False
