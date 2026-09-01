from django.db.models import F, Q, QuerySet


class SwapOrderQuerySet(QuerySet):

    def filter_by_wallet_address(self, wallet_address):
        """Complex: OR query across seller and buyer addresses."""
        if wallet_address:
            return self.filter(Q(seller_address__iexact=wallet_address) | Q(buyer_address__iexact=wallet_address))
        return self

    def filter_by_wallet_addresses(self, wallet_addresses):
        """Complex: OR query across multiple addresses for both seller and buyer."""
        if wallet_addresses:
            q = Q()
            for addr in wallet_addresses:
                q |= Q(seller_address__iexact=addr) | Q(buyer_address__iexact=addr)
            return self.filter(q)
        return self

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

    def filter_by_seller_address(self, seller_address):
        if seller_address:
            return self.filter(seller_address__iexact=seller_address)
        return self

    def filter_by_buyer_address(self, buyer_address):
        if buyer_address:
            return self.filter(buyer_address__iexact=buyer_address)
        return self

    def completed(self):
        from tokens.models.choices import SwapOrderStatus

        return self.filter(status=SwapOrderStatus.COMPLETED, tx_hash__isnull=False)

    def pending(self):
        from tokens.models.choices import SwapOrderStatus

        return self.exclude(status__in=[SwapOrderStatus.COMPLETED, SwapOrderStatus.FAILED, SwapOrderStatus.EXPIRED])

    def ready_for_execution(self):
        from tokens.models.choices import SwapOrderStatus

        return self.filter(status=SwapOrderStatus.READY)

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

    def pending_for_address(self, address: str):
        """
        Get all pending swaps where the address is either buyer or seller.

        Args:
            address: The wallet address to check (case-insensitive).

        Returns:
            QuerySet of pending SwapOrders with related data.
        """
        from tokens.models.choices import SwapOrderStatus

        return self.filter(
            Q(seller_address__iexact=address) | Q(buyer_address__iexact=address),
            status__in=[
                SwapOrderStatus.CREATED,
                SwapOrderStatus.SELLER_SIGNED,
                SwapOrderStatus.BUYER_SIGNED,
            ],
        ).with_related()

    def pending_for_wallet_ids(self, wallet_ids):
        """Return pending swaps tied to the caller's exact wallet rows."""
        from tokens.models.choices import SwapOrderStatus

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

    def stale_pending(self, expires_before):
        """
        Get pending swap orders that have expired.

        Args:
            expires_before: datetime before which orders are considered stale.

        Returns:
            QuerySet of stale pending SwapOrders.
        """
        from tokens.models.choices import SwapOrderStatus

        return self.filter(
            expires_at__lt=expires_before,
            status__in=[
                SwapOrderStatus.CREATED,
                SwapOrderStatus.SELLER_SIGNED,
                SwapOrderStatus.BUYER_SIGNED,
            ],
        )
