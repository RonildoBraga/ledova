"""
KYCAID Crypto Screening Webhook Handler

Receives async crypto address/transaction screening results from KYCAID.
Documentation: https://docs.kycaid.com/#crypto-services
"""

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from compliance.models import TransactionScreening
from compliance.services.crypto_screening import CryptoScreeningService
from integrations.kyc.constants import PROVIDER_KYCAID
from integrations.kycaid.client import KYCAIDService
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


@method_decorator(csrf_exempt, name="dispatch")
class KYCAIDCryptoWebhookView(APIView):
    """
    Handle crypto screening webhooks from KYCAID.

    POST /webhooks/kycaid/crypto/

    Receives SERVICE_RESULT callbacks for:
    - CRYPTO_ADDRESS_CHECK: Address verification result
    - CRYPTO_TRANSACTION_CHECK: Transaction verification result
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        signature = request.headers.get("x-data-integrity", "")

        logger.info(f"{LoggingContext.KYCAID_CRYPTO} Received webhook, signature present: {bool(signature)}")

        kycaid_service = KYCAIDService()
        if not kycaid_service.verify_crypto_webhook_signature(request.body, signature):
            logger.warning(f"{LoggingContext.KYCAID_CRYPTO} Invalid webhook signature")
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = request.data
            request_id = data.get("request_id")
            result = data.get("result", {})

            logger.info(
                f"{LoggingContext.KYCAID_CRYPTO} Processing result for request {request_id}, "
                f"risk_score={result.get('risk_score', 0)}"
            )

            try:
                screening = TransactionScreening.objects.get(
                    provider=PROVIDER_KYCAID,
                    provider_transaction_id=request_id,
                )
            except TransactionScreening.DoesNotExist:
                logger.warning(f"{LoggingContext.KYCAID_CRYPTO} Screening not found for request_id: {request_id}")
                return Response({"success": True}, status=status.HTTP_200_OK)

            # Normalize KYCAID payload to the format expected by the service
            # KYCAID: {"result": {"risk_score": 0.85, "signals": [...]}}
            # Service expects: {"riskScore": 0.85, "signals": [...]}
            normalized_data = {
                "riskScore": result.get("risk_score", 0),
                "signals": result.get("signals", []),
                "raw": data,
            }

            service = CryptoScreeningService()
            service.process_webhook_result(screening, normalized_data)

            logger.info(
                f"{LoggingContext.KYCAID_CRYPTO} Updated screening {screening.pk}: "
                f"result={screening.result}, risk_score={screening.risk_score}"
            )

            return Response({"success": True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"{LoggingContext.KYCAID_CRYPTO} Error processing webhook: {str(e)}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
