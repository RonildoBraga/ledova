import logging
from datetime import timedelta

from django.utils import timezone
from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from tokens.models import ShareToken, ShareTokenStatus
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)

PENDING_DEPLOYMENT_AGE = timedelta(minutes=10)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def deploy_share_token_task(token_uuid: str):
    token = ShareToken.objects.select_related("company").filter(uuid=token_uuid).first()
    if token is None:
        logger.error(f"Token not found: {token_uuid}")
        return {"success": False, "error": "Token not found"}
    if token.status != ShareTokenStatus.DEPLOYING:
        logger.warning(f"Token {token_uuid} not deployable: {token.status}")
        return {"success": False, "error": "Token is not in deploying state"}

    result = ShareTokenService().deploy_token(token)
    logger.info(f"Deployed {token.symbol} at {result['contract_address']}")
    return {"success": True, **result}


@app.periodic(cron="*/5 * * * *")
@app.task
def check_pending_token_deployments(timestamp: int = 0):
    pending = ShareToken.objects.filter(
        status=ShareTokenStatus.DEPLOYING,
        updated_at__lt=timezone.now() - PENDING_DEPLOYMENT_AGE,
    ).select_related("company")

    service = ShareTokenService()
    checked = 0
    resolved = 0

    for token in pending:
        checked += 1
        try:
            contract_address = service.resolve_pending_deployment(token)
        except Exception as e:
            logger.error(f"Check failed for {token.uuid}: {e}")
            continue
        if contract_address:
            resolved += 1
            logger.info(f"Resolved {token.symbol} at {contract_address}")

    logger.info(f"Pending deployments: checked={checked}, resolved={resolved}")
    return {"checked": checked, "resolved": resolved}
