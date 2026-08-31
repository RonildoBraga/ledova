import logging

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext
from tokens.models import ShareIssuance
from tokens.models.choices import IssuanceRequestStatus
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def execute_share_issuance_request_task(request_uuid: str):
    from tokens.models import ShareIssuanceRequest

    issuance = None

    try:
        request = ShareIssuanceRequest.objects.select_related("token", "token__company").get(uuid=request_uuid)
    except ShareIssuanceRequest.DoesNotExist:
        logger.error(f"{LoggingContext.TOKEN} Request not found: {request_uuid}")
        return {"success": False, "error": "Request not found"}

    try:
        if request.status not in [IssuanceRequestStatus.APPROVED, IssuanceRequestStatus.FAILED]:
            logger.warning(f"{LoggingContext.TOKEN} Request {request_uuid} not executable: {request.status}")
            return {"success": False, "error": "Request is not in executable state"}

        token = request.token

        if not token.contract_address:
            logger.error(f"{LoggingContext.TOKEN} Token {token.symbol} not deployed")
            request.mark_failed("Token is not deployed on blockchain")
            return {"success": False, "error": "Token is not deployed"}

        if token.status != "deployed":
            logger.error(f"{LoggingContext.TOKEN} Token {token.symbol} not in deployed status")
            request.mark_failed("Token is not in deployed status")
            return {"success": False, "error": "Token is not in deployed status"}

        request.mark_executing()

        issuance = ShareIssuance.objects.create(
            token=token,
            recipient_address=request.recipient_address,
            recipient_name=request.recipient_name,
            amount=str(request.amount),
            issuance_type=request.issuance_type,
            reason=f"Issuance request: {request.reason}",
        )

        logger.info(
            f"{LoggingContext.TOKEN} Executing issuance {token.symbol}: "
            f"{request.amount} shares to {request.recipient_address}"
        )

        service = ShareTokenService()
        result = service.mint_shares(issuance)

        token.total_supply = str(int(token.total_supply) + request.amount)
        token.save(update_fields=["total_supply", "updated_at"])

        request.mark_executed(issuance)

        logger.info(f"{LoggingContext.TOKEN} Issuance request complete: {token.symbol}")

        return {
            "success": True,
            "tx_hash": result["tx_hash"],
            "block_number": result["block_number"],
        }

    except Exception as exc:
        logger.error(f"{LoggingContext.TOKEN} Execution failed: {exc}")

        if issuance:
            issuance.mark_failed(str(exc))

        try:
            request = ShareIssuanceRequest.objects.get(uuid=request_uuid)
            request.mark_failed(str(exc))
        except Exception:
            pass

        raise
