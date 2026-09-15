from django.db.models import F, Q, QuerySet

from tokens.models.choices import SwapOrderStatus


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

    def for_party_wallets(self, wallet_ids):
        if not wallet_ids:
            return self.none()
        return self.filter(Q(seller_wallet_id__in=wallet_ids) | Q(buyer_wallet_id__in=wallet_ids))

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
        return self.select_related("share_token", "payment_asset")

    def completed_for_token(self, token):
        return self.filter(share_token=token, status="completed").order_by("-completed_at", "-pk")

    def pending_for_wallet_ids(self, wallet_ids):
        return self.for_wallet_ids(wallet_ids).awaiting_signature().with_related()

    def unresolved_on_chain(self, cutoff):
        return self.filter(settlement_protocol_version=1, status=SwapOrderStatus.EXECUTING, updated_at__lt=cutoff)
