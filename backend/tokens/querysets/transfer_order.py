from django.db import models
from django.db.models import QuerySet


class TransferOrderQuerySet(QuerySet):

    def filter_by_token(self, token_uuid):
        if token_uuid:
            return self.filter(token__uuid=token_uuid)
        return self

    def filter_by_order_type(self, order_type):
        if order_type:
            return self.filter(order_type=order_type)
        return self

    def filter_by_wallet_address(self, address):
        if address:
            return self.filter(wallet_address__iexact=address)
        return self

    def ownership_bound(self):
        """Return orders whose immutable tenant and address snapshots match."""
        return self.filter(
            wallet__isnull=False,
            owner_account__isnull=False,
            wallet__user_account_id=models.F("owner_account_id"),
            wallet__address__iexact=models.F("wallet_address"),
        )

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        # Authorization is anchored to the exact wallet row selected when the
        # order was created. Address matching is unsafe because public wallet
        # addresses may be registered under more than one tenant. Legacy rows
        # without a wallet binding intentionally match nothing.
        return (
            self.ownership_bound()
            .filter(
                owner_account__user_profiles__user=user,
            )
            .distinct()
        )

    def for_token_visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.visible_to_user(user)
        return self.ownership_bound().filter(token__company__in=user_companies)

    def open(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.OPEN)

    def matched(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.MATCHED)

    def pending_signature(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.PENDING_SIGNATURE)

    def executing(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.EXECUTING)

    def completed(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.COMPLETED)

    def failed(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.FAILED)

    def cancelled(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.CANCELLED)

    def expired(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(status=TransferOrderStatus.EXPIRED)

    def active(self):
        from tokens.models.choices import TransferOrderStatus

        return self.filter(
            status__in=[
                TransferOrderStatus.OPEN,
                TransferOrderStatus.MATCHED,
                TransferOrderStatus.PENDING_SIGNATURE,
                TransferOrderStatus.EXECUTING,
            ]
        )

    def buy_orders(self):
        from tokens.models.choices import TransferOrderType

        return self.filter(order_type=TransferOrderType.BUY)

    def sell_orders(self):
        from tokens.models.choices import TransferOrderType

        return self.filter(order_type=TransferOrderType.SELL)

    def matchable(self):
        """Orders that can be matched (open or partially filled)."""
        from tokens.models.choices import TransferOrderStatus

        return self.filter(
            status__in=[TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED],
        )

    def open_or_partial(self):
        """Orders that can still receive matches (open or partially filled)."""
        from tokens.models.choices import TransferOrderStatus

        return self.filter(
            status__in=[TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED],
        )

    def committed_sell_quantity(self, token, wallet_address, exclude_uuid=None) -> int:
        """
        Calculate the total quantity committed to open SELL orders for a wallet.

        This is used to determine the available balance for new sell orders
        by subtracting committed quantity from the total token balance.

        Args:
            token: The ShareToken to filter by.
            wallet_address: The wallet address to check.
            exclude_uuid: Optional order UUID to exclude (e.g., the order being modified).

        Returns:
            Total uncommitted quantity (quantity - filled_quantity) across matching orders.
        """
        from tokens.models.choices import TransferOrderStatus, TransferOrderType

        qs = self.ownership_bound().filter(
            token=token,
            wallet_address__iexact=wallet_address,
            order_type=TransferOrderType.SELL,
            status__in=[TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED],
        )

        if exclude_uuid:
            qs = qs.exclude(uuid=exclude_uuid)

        result = qs.aggregate(total=models.Sum(models.F("quantity") - models.F("filled_quantity")))["total"]

        return result or 0

    def order_book_levels(self, token, order_type: str, limit: int = 20):
        """
        Get aggregated order book levels for a token.

        Groups orders by price and calculates total remaining quantity at each level.
        Used to build order book displays.

        Args:
            token: The ShareToken to get order book for.
            order_type: "BUY" or "SELL".
            limit: Maximum number of price levels to return.

        Returns:
            QuerySet with price_per_share, total_quantity, and order_count.
        """
        from tokens.models.choices import TransferOrderType

        qs = self.ownership_bound().open().filter(token=token)

        if order_type == TransferOrderType.BUY:
            qs = qs.buy_orders().order_by("-price_per_share")
        else:
            qs = qs.sell_orders().order_by("price_per_share")

        return qs.values("price_per_share").annotate(
            total_quantity=models.Sum(models.F("quantity") - models.F("filled_quantity")),
            order_count=models.Count("uuid"),
        )[:limit]

    def best_bid(self, token):
        """
        Get the best (highest) buy order for a token.

        Args:
            token: The ShareToken to find best bid for.

        Returns:
            The best bid TransferOrder or None.
        """
        return self.ownership_bound().open().buy_orders().filter(token=token).order_by("-price_per_share").first()

    def best_ask(self, token):
        """
        Get the best (lowest) sell order for a token.

        Args:
            token: The ShareToken to find best ask for.

        Returns:
            The best ask TransferOrder or None.
        """
        return self.ownership_bound().open().sell_orders().filter(token=token).order_by("price_per_share").first()

    def with_relations(self):
        return self.select_related(
            "token",
            "token__company",
            "payment_token",
            "wallet",
            "wallet__user_account",
            "owner_account",
            "matched_order",
            "signature_request",
        )

    def search(self, query):
        if not query:
            return self
        return self.filter(
            models.Q(wallet_address__icontains=query)
            | models.Q(token__symbol__icontains=query)
            | models.Q(token__name__icontains=query)
            | models.Q(tx_hash__icontains=query)
        )
