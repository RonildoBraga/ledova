"""
KYCAID Webhook Handler

Receives verification status updates from KYCAID.
Documentation: https://docs.kycaid.com/#webhooks
"""

import logging

from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.kyc.constants import (
    KYCAID_EVENT_VERIFICATION_COMPLETED,
    KYCAID_EVENT_VERIFICATION_STATUS_CHANGED,
    REVIEW_GREEN,
    STATUS_PENDING,
)
from integrations.kycaid.client import KYCAIDService
from users.models.user_profile import UserProfile
from users.services import IdentityVerificationService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class KYCAIDWebhookView(APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        signature = request.headers.get("x-data-integrity", "")

        logger.info(f"Received webhook request, signature present: {bool(signature)}")

        kycaid_service = KYCAIDService()
        if not kycaid_service.verify_webhook_signature(request.body, signature):
            logger.warning(f"Invalid webhook signature. Body length: {len(request.body)}")
            return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

        logger.info("Signature verified successfully")

        try:
            data = request.data
            event_type = data.get("type")
            applicant_id = data.get("applicant_id")
            verification_id = data.get("verification_id")

            logger.info(f"Received webhook: {event_type} for applicant {applicant_id}, verification: {verification_id}")

            if not applicant_id:
                logger.warning("Missing applicant_id in webhook payload")
                return Response({"error": "Missing applicant_id"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user_profile = UserProfile.objects.get(kycaid_applicant_id=applicant_id)
            except (UserProfile.DoesNotExist, ValueError, ValidationError):
                logger.warning(f"User profile not found for KYCAID applicant: {applicant_id}")
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if event_type == KYCAID_EVENT_VERIFICATION_COMPLETED:
                normalized = kycaid_service.normalize_webhook(data)
                IdentityVerificationService.update_status_from_normalized(user_profile, normalized)
                logger.info(f"Processed VERIFICATION_COMPLETED for {applicant_id}")

                # Populate profile with verified data after approval
                if normalized.review_result == REVIEW_GREEN:
                    try:
                        applicant_data = kycaid_service.get_applicant_data(applicant_id)
                        extracted_data = kycaid_service.extract_verified_data(applicant_data)
                        IdentityVerificationService.populate_profile(user_profile, extracted_data)
                        logger.info(f"Populated profile for {applicant_id}")
                    except Exception as e:
                        logger.warning(f"Failed to populate profile for {applicant_id}: {e}")

            elif event_type == KYCAID_EVENT_VERIFICATION_STATUS_CHANGED:
                new_status = data.get("status", STATUS_PENDING)
                user_profile.verification_status = new_status
                user_profile.save(update_fields=["verification_status", "updated_at"])
                logger.info(f"Updated status to {new_status} for {applicant_id}")

            else:
                logger.info(f"Unhandled webhook type: {event_type}")

            return Response({"success": True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
