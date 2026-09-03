"""
SumSub Webhook Handler

Receives verification status updates from SumSub.
Documentation: https://docs.sumsub.com/reference/webhooks
"""

import logging

from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.kyc.constants import (
    STATUS_INIT,
    STATUS_ON_HOLD,
    STATUS_PENDING,
    SUMSUB_EVENT_APPLICANT_CREATED,
    SUMSUB_EVENT_APPLICANT_ON_HOLD,
    SUMSUB_EVENT_APPLICANT_PENDING,
    SUMSUB_EVENT_APPLICANT_REVIEWED,
)
from integrations.sumsub import SumSubService
from users.models.user_profile import UserProfile
from users.services import IdentityVerificationService

logger = logging.getLogger("ledova_backend")


@method_decorator(csrf_exempt, name="dispatch")
class SumSubWebhookView(APIView):
    """
    Handle webhooks from SumSub.

    POST /api/users/webhooks/sumsub/

    Webhook Types:
    - applicantCreated
    - applicantPending
    - applicantReviewed
    - applicantOnHold
    - applicantActionPending
    - applicantActionReviewed
    """

    authentication_classes = []
    permission_classes = []
    # SumSub sends camelCase keys (applicantId, externalUserId, reviewResult, reviewStatus); the
    # project-wide CamelCase parser would underscore them, so this view reads the payload verbatim.
    parser_classes = [JSONParser]

    def post(self, request):
        signature = request.headers.get("X-Payload-Digest", "")

        logger.info(f"[WEBHOOK] Received webhook request, signature present: {bool(signature)}")

        sumsub_service = SumSubService()
        if not sumsub_service.verify_webhook_signature(request.body, signature):
            logger.warning(f"[WEBHOOK] Invalid webhook signature. Body length: {len(request.body)}")
            return Response({"error": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

        logger.info("[WEBHOOK] Signature verified successfully")

        try:
            data = request.data
            webhook_type = data.get("type")
            applicant_id = data.get("applicantId")
            external_user_id = data.get("externalUserId")

            logger.info(
                f"[WEBHOOK] Received SumSub webhook: {webhook_type} for applicant {applicant_id}, "
                f"externalUserId: {external_user_id}"
            )

            if not external_user_id:
                logger.warning(f"[WEBHOOK] Missing externalUserId for applicant {applicant_id}")
                return Response({"error": "Missing externalUserId"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user_profile = UserProfile.objects.get(uuid=external_user_id)

                if user_profile.sumsub_applicant_id != applicant_id:
                    user_profile.sumsub_applicant_id = applicant_id
                    user_profile.save(update_fields=["sumsub_applicant_id"])
                    logger.info(f"[WEBHOOK] Updated applicant ID to {applicant_id} for profile {external_user_id}")

            except (UserProfile.DoesNotExist, ValueError, ValidationError):
                logger.warning(f"[WEBHOOK] User profile not found or invalid UUID: {external_user_id}")
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if webhook_type == SUMSUB_EVENT_APPLICANT_CREATED:
                user_profile.sumsub_verification_status = STATUS_INIT
                user_profile.save()

            elif webhook_type == SUMSUB_EVENT_APPLICANT_PENDING:
                user_profile.sumsub_verification_status = STATUS_PENDING
                user_profile.save()

            elif webhook_type == SUMSUB_EVENT_APPLICANT_REVIEWED:
                IdentityVerificationService.update_status_from_normalized(
                    user_profile, sumsub_service.normalize_webhook(data)
                )
                logger.info(f"[WEBHOOK] Processed applicantReviewed for {applicant_id}")

            elif webhook_type == SUMSUB_EVENT_APPLICANT_ON_HOLD:
                user_profile.sumsub_verification_status = STATUS_ON_HOLD
                user_profile.save()

            else:
                logger.info(f"[WEBHOOK] Unhandled webhook type: {webhook_type}")

            logger.info(f"[WEBHOOK] Updated user profile {user_profile.user.id} from webhook")

            return Response({"success": True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
