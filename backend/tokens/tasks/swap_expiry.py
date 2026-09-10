import logging

from ledova_backend.procrastinate_app import app
from tokens.services.swap_expiry import expire_unclaimed_swaps

logger = logging.getLogger(__name__)


@app.periodic(cron="* * * * *")
@app.task
def expire_unclaimed_matches(timestamp: int = 0):
    result = expire_unclaimed_swaps()
    logger.info(
        "Swap expiry checked: %s, expired: %s, retained: %s",
        result["checked"],
        result["expired"],
        result["retained"],
    )
    return result
