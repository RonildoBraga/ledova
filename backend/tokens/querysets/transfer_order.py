from django.db import models
from django.db.models import QuerySet

from tokens.models.choices import TransferOrderStatus, TransferOrderType


class TransferOrderQuerySet(QuerySet):
    def filter_by_token(self, token_uuid):
        if token_uuid:
            return self.filter(token__uuid=token_uuid)
        return self

    def filter_by_order_type(self, order_type):
        if order_type:
            return self.filter(order_type=order_type)
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

    def open(self):
        return self.filter(status=TransferOrderStatus.OPEN)

    def completed(self):
        return self.filter(status=TransferOrderStatus.COMPLETED)

    def active(self):
        return self.filter(
            status__in=[
                TransferOrderStatus.OPEN,
                TransferOrderStatus.MATCHED,
                TransferOrderStatus.PENDING_SIGNATURE,
                TransferOrderStatus.EXECUTING,
            ]
        )

    def buy_orders(self):
        return self.filter(order_type=TransferOrderType.BUY)

    def sell_orders(self):
        return self.filter(order_type=TransferOrderType.SELL)

    def open_or_partial(self):
        """Orders that can still receive matches (open or partially filled)."""
        return self.filter(
            status__in=[TransferOrderStatus.OPEN, TransferOrderStatus.PARTIALLY_FILLED],
        )

    def committed_sell_quantity(self, token, wallet_address, exclude_uuid=None) -> int:
        """Quantity locked in open SELL orders; subtracted from the token balance to size new sells."""
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
        """Remaining quantity aggregated per price level."""
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
        return self.ownership_bound().open().buy_orders().filter(token=token).order_by("-price_per_share").first()

    def best_ask(self, token):
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
