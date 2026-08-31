import logging
from typing import Optional

from tokens.models import TransferOrder, TransferOrderStatus, TransferOrderType

logger = logging.getLogger(__name__)


class MatchingService:
    def find_best_match_with_partial_fill(self, incoming_order: TransferOrder) -> Optional[TransferOrder]:
        """
        Find the best matching order considering partial fill requirements.

        Finds a single best match that satisfies both parties' min_quantity constraints.

        Args:
            incoming_order: The order to find a match for.

        Returns:
            The best matching order, or None if no valid match exists.
        """
        opposite_type = (
            TransferOrderType.SELL if incoming_order.order_type == TransferOrderType.BUY else TransferOrderType.BUY
        )

        candidates = TransferOrder.objects.filter(
            token=incoming_order.token,
            order_type=opposite_type,
            status__in=[TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED],
        ).exclude(wallet_address__iexact=incoming_order.wallet_address)

        if incoming_order.order_type == TransferOrderType.BUY:
            candidates = candidates.filter(price_per_share__lte=incoming_order.price_per_share).order_by(
                "price_per_share", "created_at"
            )
        else:
            candidates = candidates.filter(price_per_share__gte=incoming_order.price_per_share).order_by(
                "-price_per_share", "created_at"
            )

        incoming_min = incoming_order.effective_min_quantity
        incoming_remaining = incoming_order.remaining_quantity

        for candidate in candidates:
            candidate_remaining = candidate.remaining_quantity
            candidate_min = candidate.effective_min_quantity

            match_qty = min(incoming_remaining, candidate_remaining)

            if incoming_min > 0 and match_qty < incoming_min:
                continue
            if candidate_min > 0 and match_qty < candidate_min:
                continue

            return candidate

        return None
