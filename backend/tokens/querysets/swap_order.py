from django.db.models import F, Q, QuerySet

from tokens.models.choices import SwapOrderStatus
from wallets.models import Wallet


class SwapOrderQuerySet(QuerySet):
    def for_wallet_ids(self, wallet_ids):
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

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        wallet_ids = list(Wallet.objects.visible_to_user(user).verified_evm().values_list("uuid", flat=True))
        return self.for_wallet_ids(wallet_ids)

    def awaiting_signature(self):
        return self.filter(
            status__in=[
                SwapOrderStatus.CREATED,
                SwapOrderStatus.SELLER_SIGNED,
                SwapOrderStatus.BUYER_SIGNED,
            ],
        )

    def pending(self):
        return self.exclude(status__in=[SwapOrderStatus.COMPLETED, SwapOrderStatus.FAILED, SwapOrderStatus.EXPIRED])

    def with_related(self):
        return self.select_related("share_token", "payment_asset", "sell_order", "buy_order")

    def last_completed_for_token(self, token):
        return self.filter(share_token=token, status="completed").order_by("-completed_at").first()

    def pending_for_wallet_ids(self, wallet_ids):
        return self.for_wallet_ids(wallet_ids).awaiting_signature().with_related()

    def for_transfer_order(self, order):
        return self.filter(Q(sell_order=order) | Q(buy_order=order)).first()

    def unresolved_on_chain(self, cutoff):
        return self.filter(status=SwapOrderStatus.EXECUTING, updated_at__lt=cutoff)
