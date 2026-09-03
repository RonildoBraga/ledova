import logging

from django.apps import apps
from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from shared.utils.logging_utils import LoggingContext
from tokens.exceptions import CompanyNotReadyException, InvalidTokenStateException
from tokens.services import ShareTokenService

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=4, wait=30))
def execute_review_request_task(model_label: str, request_uuid: str):
    """Execute a CapitalIncreaseRequest or ShareIssuanceRequest (model_label picks which) on-chain.

    State guards answer with a result dict; chain failures re-raise so procrastinate retries the request,
    which execute_request has already marked failed.
    """
    model = apps.get_model(model_label)
    request = model.objects.select_related("token", "token__company").filter(uuid=request_uuid).first()
    if request is None:
        logger.error(f"{LoggingContext.TOKEN} Request not found: {model_label} {request_uuid}")
        return {"success": False, "error": "Request not found"}

    try:
        result = ShareTokenService().execute_request(request)
    except (InvalidTokenStateException, CompanyNotReadyException) as exc:
        logger.warning(f"{LoggingContext.TOKEN} Request {request_uuid} not executed: {exc.detail}")
        return {"success": False, "error": str(exc.detail)}

    return {"success": True, **result}
