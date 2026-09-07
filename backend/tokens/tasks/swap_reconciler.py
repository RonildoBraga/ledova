import logging
from datetime import timedelta

from django.utils import timezone

from ledova_backend.procrastinate_app import app
from tokens.models import SwapOrder
from tokens.services import AtomicSwapService

logger = logging.getLogger(__name__)

STALE_EXECUTION_AGE = timedelta(minutes=10)


@app.periodic(cron="*/5 * * * *")
@app.task
def resolve_executing_swaps(timestamp: int = 0):
    cutoff = timezone.now() - STALE_EXECUTION_AGE
    stale = SwapOrder.objects.unresolved_on_chain(cutoff).select_related("share_token", "sell_order", "buy_order")

    checked = 0
    resolved = 0
    service = None

    for swap_order in stale:
        checked += 1
        if service is None:
            service = AtomicSwapService()
        try:
            outcome = service.resolve_executing_swap(swap_order)
        except Exception as exc:
            logger.error(f"Swap {swap_order.uuid} could not be reconciled: {exc}")
            continue
        if outcome is not None:
            resolved += 1

    logger.info(f"Executing swaps checked: {checked}, resolved: {resolved}")
    return {"checked": checked, "resolved": resolved}
