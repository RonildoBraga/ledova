import logging
from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils import timezone
from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from tokens.exceptions import (
    InvalidRecipientAddressException,
    InvalidTokenStateException,
    IssuanceRefusedException,
)
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareIssuanceRequest
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)

STALE_EXECUTION_AGE = timedelta(minutes=10)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def execute_review_request_task(model_label: str, request_uuid: str, executed_by: int | None = None):
    """Execute a CapitalIncreaseRequest or ShareIssuanceRequest (model_label picks which) on-chain.

    `executed_by` is the pk of the staff user who pressed Execute; it becomes the issuance's initiated_by.
    State guards, refusals and a malformed recipient address answer with a result dict; chain failures re-raise so
    procrastinate retries the request, which execute_request has already marked failed (an unreadable paused()
    or supply happens before the claim, so the request stays approved for the retry). A retry never mints twice:
    the mint hash is on the request's ShareIssuance before the receipt is awaited and the retry resumes on it.
    """
    model = apps.get_model(model_label)
    request = model.objects.select_related("token", "token__company").filter(uuid=request_uuid).first()
    if request is None:
        logger.error(f"Request not found: {model_label} {request_uuid}")
        return {"success": False, "error": "Request not found"}
    user = get_user_model().objects.filter(pk=executed_by).first() if executed_by else None

    try:
        result = ShareTokenService().execute_request(request, executed_by=user)
    except (InvalidRecipientAddressException, InvalidTokenStateException, IssuanceRefusedException) as exc:
        logger.warning(f"Request {request_uuid} not executed: {exc.detail}")
        return {"success": False, "error": str(exc.detail)}

    return {"success": True, **result}


@app.periodic(cron="*/5 * * * *")
@app.task
def check_executing_issuance_requests(timestamp: int = 0):
    """Finish issuance and capital-increase requests a killed worker left EXECUTING after the call was sent.

    A worker dying between the call and the completion writes leaves the request EXECUTING (not executable) with
    the hash recorded (a PROCESSING issuance for a mint, a submitted BlockchainTransaction for setAuthorizedShares).
    The receipt decides: mined completes it, reverted marks it failed so it can be retried, still pending is checked
    again next run. A request with nothing recorded is only logged.
    """
    service = ShareTokenService()
    cutoff = timezone.now() - STALE_EXECUTION_AGE
    resolvers = (
        (ShareIssuanceRequest, service.resolve_executing_issuance),
        (CapitalIncreaseRequest, service.resolve_executing_capital_increase),
    )
    checked = 0
    resolved = 0

    for model, resolve in resolvers:
        stale = model.objects.filter(status=RequestStatus.EXECUTING, updated_at__lt=cutoff).select_related(
            "token", "token__company"
        )
        for request in stale:
            checked += 1
            try:
                outcome = resolve(request)
            except Exception as e:
                logger.error(f"Check failed for executing request {request.uuid}: {e}")
                continue
            if outcome:
                resolved += 1
                logger.info(f"Request {request.uuid} {outcome} by the executing sweep")

    logger.info(f"Executing requests: checked={checked}, resolved={resolved}")
    return {"checked": checked, "resolved": resolved}
