import logging

from django.utils import timezone

from ledova_backend.procrastinate_app import app
from users.services.investor_classification import purge_expired_evidence

logger = logging.getLogger(__name__)

SWEEP_BATCH = 200


@app.periodic(cron="0 3 * * *")
@app.task
def purge_classification_evidence(timestamp: int = 0):
    result = purge_expired_evidence(timezone.now(), SWEEP_BATCH)
    logger.info(f"Classification evidence purged: {result['purged']}, failed: {result['failed']}")
    return result
