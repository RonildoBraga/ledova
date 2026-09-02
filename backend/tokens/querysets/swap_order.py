from django.db.models import F, Q, QuerySet

from tokens.models.choices import SwapOrderStatus


class SwapOrderQuerySet(QuerySet):

    def for_wallet_ids(self, wallet_ids):
        """Scope swaps through exact, internally consistent order wallet FKs."""
        if not wallet_ids:
            return self.none()

        sell_order_owned = Q(
            sell_order__wallet_id__in=wallet_ids,
            sell_order__owner_account_id=F("sell_order__wallet__user_account_id"),
            sell_order__wallet_address__iexact=F("sell_order__wallet__address"),
            seller_address__iexact=F("sell_order__wallet_address"),
        )
        buy_order_owned = Q(
            buy_order__wallet_id__in=wallet_ids,
            buy_order__owner_account_id=F("buy_order__wallet__user_account_id"),
            buy_order__wallet_address__iexact=F("buy_order__wallet__address"),
            buyer_address__iexact=F("buy_order__wallet_address"),
        )
        return self.filter(sell_order_owned | buy_order_owned)

    def completed(self):
        return self.filter(status=SwapOrderStatus.COMPLETED, tx_hash__isnull=False)

    def pending(self):
        return self.exclude(status__in=[SwapOrderStatus.COMPLETED, SwapOrderStatus.FAILED, SwapOrderStatus.EXPIRED])

    def with_related(self):
        return self.select_related("share_token", "payment_token", "sell_order", "buy_order")

    def with_tokens(self):
        return self.select_related("share_token", "payment_token")

    def last_completed_for_token(self, token):
        """
        Get the most recently completed swap for a token.

        Args:
            token: The ShareToken to find last trade for.

        Returns:
            The most recent completed SwapOrder or None.
        """
        return self.filter(share_token=token, status="completed").order_by("-completed_at").first()

    def pending_for_wallet_ids(self, wallet_ids):
        """Return pending swaps tied to the caller's exact wallet rows."""
        return (
            self.for_wallet_ids(wallet_ids)
            .filter(
                status__in=[
                    SwapOrderStatus.CREATED,
                    SwapOrderStatus.SELLER_SIGNED,
                    SwapOrderStatus.BUYER_SIGNED,
                ],
            )
            .with_related()
        )

    def for_transfer_order(self, order):
        """
        Find a swap order associated with a transfer order.

        Args:
            order: The TransferOrder to find associated swap for.

        Returns:
            The associated SwapOrder or None.
        """
        return self.filter(Q(sell_order=order) | Q(buy_order=order)).first()
