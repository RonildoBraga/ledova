import logging

from django.utils import timezone

from ledova_backend.procrastinate_app import app
from tokens.services.signing_challenge import purge_expired_challenges

logger = logging.getLogger(__name__)

SWEEP_BATCH = 500


@app.periodic(cron="15 * * * *")
@app.task
def purge_signing_challenges(timestamp: int = 0):
    purged = purge_expired_challenges(timezone.now(), SWEEP_BATCH)
    logger.info(f"Signing challenges purged: {purged}")
    return {"purged": purged}
