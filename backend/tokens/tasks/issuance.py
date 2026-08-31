import logging

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext
from tokens.models import ShareIssuance
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def issue_shares_task(issuance_uuid: str):
    """Process a pending share issuance by minting tokens on-chain."""
    try:
        issuance = ShareIssuance.objects.select_related("token", "token__company").get(uuid=issuance_uuid)
    except ShareIssuance.DoesNotExist:
        logger.error(f"{LoggingContext.TOKEN} Issuance not found: {issuance_uuid}")
        return {"success": False, "error": "Issuance not found"}

    if not issuance.is_pending:
        logger.warning(f"{LoggingContext.TOKEN} Issuance {issuance_uuid} not pending: {issuance.status}")
        return {"success": False, "error": "Issuance is not in pending state"}

    service = ShareTokenService()
    result = service.mint_shares(issuance)

    return {"success": True, **result}
