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

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class KYCAIDCryptoWebhookView(APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        signature = request.headers.get("x-data-integrity", "")

        logger.info(f"Received webhook, signature present: {bool(signature)}")

        kycaid_service = KYCAIDService()
        if not kycaid_service.verify_crypto_webhook_signature(request.body, signature):
            logger.warning("Invalid webhook signature")
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = request.data
            request_id = data.get("request_id")
            result = data.get("result", {})

            logger.info(f"Processing result for request {request_id}, risk_score={result.get('risk_score', 0)}")

            try:
                screening = TransactionScreening.objects.get(
                    provider=PROVIDER_KYCAID,
                    provider_transaction_id=request_id,
                )
            except TransactionScreening.DoesNotExist:
                logger.warning(f"Screening not found for request_id: {request_id}")
                return Response({"success": True}, status=status.HTTP_200_OK)

            normalized_data = {
                "riskScore": result.get("risk_score", 0),
                "signals": result.get("signals", []),
                "raw": data,
            }

            service = CryptoScreeningService()
            service.process_webhook_result(screening, normalized_data)

            logger.info(
                f"Updated screening {screening.pk}: result={screening.result}, risk_score={screening.risk_score}"
            )

            return Response({"success": True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
