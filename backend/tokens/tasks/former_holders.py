import logging

from procrastinate import RetryStrategy

from ledova_backend.procrastinate_app import app
from tokens.models import ShareToken, ShareTokenStatus
from tokens.services.former_holders import fold_former_holders, purge_former_holders

logger = logging.getLogger(__name__)

FOLDABLE = (ShareTokenStatus.DEPLOYED, ShareTokenStatus.PAUSED)


@app.periodic(cron="20 */6 * * *")
@app.task(retry=RetryStrategy(max_attempts=3, wait=300))
def fold_every_share_class(timestamp: int = 0):
    folded = 0
    unreadable = 0
    for token in ShareToken.objects.filter(status__in=FOLDABLE).exclude(contract_address=""):
        try:
            fold_former_holders(token)
            folded += 1
        except Exception as exc:
            unreadable += 1
            logger.error("The former-members fold could not read %s: %s", token.uuid, type(exc).__name__)

    if unreadable:
        logger.warning(
            f"The former-members fold reached {folded} share classes and could not read "
            f"{unreadable}, so those registers report the date they last succeeded"
        )
        raise RuntimeError(f"Former-member fold could not read {unreadable} share classes.")
    return {"folded": folded}


@app.periodic(cron="40 3 * * *")
@app.task(retry=RetryStrategy(max_attempts=3, wait=600))
def purge_former_members_past_the_clock(timestamp: int = 0):
    removed = purge_former_holders()
    return {"removed": removed}
