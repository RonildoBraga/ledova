import logging

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext
from tokens.models import (
    CapitalIncreaseRequest,
    CapitalIncreaseStatus,
    IssuanceType,
    ShareIssuance,
)
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def execute_capital_increase_task(request_uuid: str):
    issuance = None

    try:
        request = CapitalIncreaseRequest.objects.select_related("token", "token__company").get(uuid=request_uuid)
    except CapitalIncreaseRequest.DoesNotExist:
        logger.error(f"{LoggingContext.TOKEN} Request not found: {request_uuid}")
        return {"success": False, "error": "Request not found"}

    try:
        if request.status not in [CapitalIncreaseStatus.APPROVED, CapitalIncreaseStatus.FAILED]:
            logger.warning(f"{LoggingContext.TOKEN} Request {request_uuid} not executable: {request.status}")
            return {"success": False, "error": "Request is not in executable state"}

        token = request.token
        company = token.company

        if not token.contract_address:
            logger.error(f"{LoggingContext.TOKEN} Token {token.symbol} not deployed")
            request.mark_failed("Token is not deployed on blockchain")
            return {"success": False, "error": "Token is not deployed"}

        primary_wallet = company.get_primary_wallet()
        if not primary_wallet:
            logger.error(f"{LoggingContext.TOKEN} No primary ETH wallet for {company.name}")
            request.mark_failed("Company has no operator wallet or verified ETH wallet")
            return {"success": False, "error": "Company has no operator wallet or verified ETH wallet"}

        request.mark_executing()

        issuance = ShareIssuance.objects.create(
            token=token,
            recipient_address=primary_wallet.address,
            recipient_name=f"{company.name} Primary Wallet",
            amount=str(request.additional_shares),
            issuance_type=IssuanceType.ADDITIONAL,
            reason=f"Capital increase: {request.purpose}",
        )
        issuance.mark_processing()

        logger.info(f"{LoggingContext.TOKEN} Executing {token.symbol} +{request.additional_shares} shares")

        service = ShareTokenService()
        result = service.increase_authorized_shares(
            contract_address=token.contract_address,
            additional_shares=request.additional_shares,
            company_wallet=primary_wallet.address,
        )

        issuance.mark_completed(
            tx_hash=result["mint_tx_hash"],
            block_number=result["block_number"],
            gas_used=result["gas_used"],
        )

        token.total_supply = str(int(token.total_supply) + request.additional_shares)
        token.save(update_fields=["total_supply", "updated_at"])

        request.mark_executed(issuance)

        logger.info(f"{LoggingContext.TOKEN} Capital increase complete: {token.symbol}")

        return {
            "success": True,
            "set_authorized_tx_hash": result["set_authorized_tx_hash"],
            "mint_tx_hash": result["mint_tx_hash"],
            "new_authorized_total": result["new_authorized_total"],
        }

    except Exception as exc:
        logger.error(f"{LoggingContext.TOKEN} Execution failed: {exc}")

        if issuance:
            issuance.mark_failed(str(exc))

        try:
            request = CapitalIncreaseRequest.objects.get(uuid=request_uuid)
            request.mark_failed(str(exc))
        except Exception:
            pass

        raise
