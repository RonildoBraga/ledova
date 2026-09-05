import logging
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from integrations.kyc import get_kyc_provider
from integrations.kyc.base import (
    KYCProvider,
    NormalizedVerificationResult,
    VerificationSession,
)
from integrations.kyc.constants import (
    PROVIDER_KYCAID,
    PROVIDER_SUMSUB,
    REVIEW_GREEN,
    REVIEW_RED,
    REVIEW_YELLOW,
)
from shared.models.country import Country
from users.models.user_profile import UserProfile

logger = logging.getLogger(__name__)

REVIEW_OUTCOME_MESSAGES = {
    REVIEW_GREEN: ("Identity verified", "Your identity has been verified."),
    REVIEW_RED: (
        "Verification needs attention",
        "We could not verify your identity. Please review your verification details.",
    ),
    REVIEW_YELLOW: ("Verification needs attention", "Your identity verification needs another attempt."),
}


class VerificationTokenGenerationException(APIException):
    status_code = 502
    default_detail = "Unable to initialize verification. Please try again."
    default_code = "verification_token_generation_failed"


class IdentityVerificationService:

    @staticmethod
    def create_applicant(kyc_provider: KYCProvider, user_profile: UserProfile) -> dict:
        try:
            external_id = str(user_profile.uuid)
            result = kyc_provider.create_applicant(
                external_id,
                first_name=user_profile.full_name.split()[0] if user_profile.full_name else None,
                last_name=user_profile.full_name.split()[-1] if user_profile.full_name else None,
                dob=str(user_profile.date_of_birth) if user_profile.date_of_birth else None,
                email=user_profile.user.email,
            )

            provider_name = kyc_provider.get_provider_name()
            if provider_name == PROVIDER_KYCAID:
                user_profile.kycaid_applicant_id = result["applicant_id"]
            elif provider_name == PROVIDER_SUMSUB:
                user_profile.sumsub_applicant_id = result.get("applicant_id")

            user_profile.kyc_provider = provider_name
            user_profile.save()

            return result
        except Exception as e:
            logger.error(
                f"Failed to create applicant for user profile {user_profile.uuid}: {e}",
                exc_info=True,
            )
            raise VerificationTokenGenerationException("Unable to initialize verification. Please try again later.")

    @staticmethod
    def get_verification_session(user_profile: UserProfile) -> VerificationSession:
        kyc_provider = get_kyc_provider()
        external_id = str(user_profile.uuid)

        if not user_profile.active_applicant_id:
            IdentityVerificationService.create_applicant(kyc_provider, user_profile)
            user_profile.refresh_from_db()

        applicant_id = user_profile.active_applicant_id
        try:
            return kyc_provider.generate_session(applicant_id, external_id)
        except Exception as e:
            logger.warning(f"generate_session failed for applicant {applicant_id}, re-creating: {e}")
            provider_name = kyc_provider.get_provider_name()
            if provider_name == PROVIDER_KYCAID:
                user_profile.kycaid_applicant_id = None
            elif provider_name == PROVIDER_SUMSUB:
                user_profile.sumsub_applicant_id = None
            user_profile.save()

            IdentityVerificationService.create_applicant(kyc_provider, user_profile)
            user_profile.refresh_from_db()
            applicant_id = user_profile.active_applicant_id
            return kyc_provider.generate_session(applicant_id, external_id)

    @staticmethod
    def get_verification_status(user_profile: UserProfile) -> dict:
        kyc_provider = get_kyc_provider()
        applicant_id = user_profile.active_applicant_id

        if applicant_id and not user_profile.is_id_verified:
            try:
                status_data = kyc_provider.get_applicant_status(applicant_id)
                normalized = kyc_provider.normalize_webhook(status_data)
                if normalized.review_result:
                    IdentityVerificationService.update_status_from_normalized(user_profile, normalized)
            except Exception as e:
                logger.warning(f"Failed to fetch live status for applicant {applicant_id}, using cached data: {e}")

        response_data = {
            "provider": user_profile.kyc_provider,
            "applicantId": applicant_id,
            "status": user_profile.verification_status,
            "reviewResult": user_profile.review_result,
            "reviewAnswer": user_profile.review_result,
            "isVerified": user_profile.is_id_verified,
            "verifiedAt": user_profile.verified_at,
            "rejectionLabels": user_profile.rejection_labels or [],
            "needsRetry": user_profile.needs_verification_retry,
            "extractedData": None,
        }

        if user_profile.is_id_verified and applicant_id:
            try:
                applicant_data = kyc_provider.get_applicant_data(applicant_id)
                extracted_data = kyc_provider.extract_verified_data(applicant_data)
                response_data["extractedData"] = extracted_data
                IdentityVerificationService.populate_profile(user_profile, extracted_data)
            except Exception as e:
                logger.warning(f"Failed to extract verified data for applicant {applicant_id}: {e}")

        return response_data

    @staticmethod
    def update_status_from_normalized(user_profile: UserProfile, normalized: NormalizedVerificationResult) -> bool:
        previous_result = user_profile.review_result
        user_profile.verification_status = normalized.verification_status
        user_profile.review_result = normalized.review_result
        user_profile.rejection_labels = normalized.rejection_labels or None

        if user_profile.kyc_provider == PROVIDER_SUMSUB:
            user_profile.sumsub_verification_status = normalized.verification_status

        if normalized.document_type:
            user_profile.id_document_type = normalized.document_type
        if normalized.document_country:
            user_profile.id_document_country = normalized.document_country

        was_verified = user_profile.is_id_verified

        if normalized.review_result == REVIEW_GREEN and not user_profile.is_id_verified:
            user_profile.is_id_verified = True
            user_profile.verified_at = timezone.now()
            logger.info(f"User {user_profile.user.id} verified successfully")
        elif normalized.review_result in [REVIEW_RED, REVIEW_YELLOW]:
            user_profile.is_id_verified = False
            user_profile.verified_at = None

        with transaction.atomic():
            user_profile.save()

            if normalized.review_result == REVIEW_GREEN and not was_verified:
                IdentityVerificationService._process_verified_customer(user_profile, normalized.pep_data)

            message = REVIEW_OUTCOME_MESSAGES.get(normalized.review_result)
            if message and normalized.review_result != previous_result:

                from users.tasks.notifications import send_push_notification

                title, body = message
                send_push_notification.defer(
                    user_id=str(user_profile.user_id), title=title, body=body, notification_type="general"
                )

        return user_profile.is_id_verified

    @staticmethod
    def _process_verified_customer(user_profile, pep_data: Dict[str, Any]) -> None:
        from compliance.constants import FATF_BLACKLIST_COUNTRIES, PEP_REJECTION_TYPES
        from users.constants import ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_REJECTED

        pep_type = pep_data.get("pep_type", "none")

        user_account = user_profile.user_accounts.first()
        if not user_account:
            logger.warning(f"No user_account found for user_profile {user_profile.uuid}")
            return

        if pep_type in PEP_REJECTION_TYPES:
            user_account.account_status = ACCOUNT_STATUS_REJECTED
            user_account.rejection_reason = "pep_policy"
            user_account.save()
            logger.info(f"Account {user_account.uuid} rejected: PEP type {pep_type}")
            return

        citizenship = user_profile.citizenship_country
        if citizenship and citizenship.code and citizenship.code.upper() in FATF_BLACKLIST_COUNTRIES:
            user_account.account_status = ACCOUNT_STATUS_REJECTED
            user_account.rejection_reason = "fatf_blacklist"
            user_account.save()
            logger.info(f"Account {user_account.uuid} rejected: FATF black-list country {citizenship.code}")
            return

        user_account.account_status = ACCOUNT_STATUS_ACTIVE
        user_account.save()

        IdentityVerificationService._trigger_risk_assessment(user_account, pep_data)

    @staticmethod
    def _trigger_risk_assessment(user_account, pep_data: Dict[str, Any]) -> None:
        from compliance.services.risk_assessment import RiskAssessmentService

        try:

            with transaction.atomic():
                RiskAssessmentService.calculate_and_create(user_account=user_account, pep_data=pep_data)
            logger.info(f"Triggered risk assessment for account {user_account.uuid}")
        except Exception as e:
            logger.error(
                f"Error triggering risk assessment for account {user_account.uuid}: {e}",
                exc_info=True,
            )

    @staticmethod
    def populate_profile(user_profile: UserProfile, extracted_data: Dict[str, Optional[str]]) -> bool:
        profile_updated = False

        full_name = extracted_data.get("fullName")
        address = extracted_data.get("address")
        date_of_birth = extracted_data.get("dateOfBirth")
        residence_country = extracted_data.get("residenceCountry")

        if full_name and not user_profile.full_name:
            user_profile.full_name = full_name
            profile_updated = True

        if address and not user_profile.residential_address:
            user_profile.residential_address = address
            profile_updated = True

        if date_of_birth and not user_profile.date_of_birth:
            user_profile.date_of_birth = date_of_birth
            profile_updated = True

        if residence_country and not user_profile.residence_country:
            user_profile.residence_country = Country.get_or_create_for_code(residence_country)
            profile_updated = True

        if profile_updated:
            user_profile.save()

        return profile_updated
