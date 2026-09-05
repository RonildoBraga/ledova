from django.db import models
from django.db.models import OuterRef, QuerySet, Subquery

from tokens.models.choices import SwapOrderStatus


class ShareTokenQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.visible_to_user(user)
        return self.filter(company__in=user_companies)

    def manageable_by_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        from companies.models import Company

        user_companies = Company.objects.manageable_by_user(user)
        return self.filter(company__in=user_companies)

    def deployed(self):
        return self.filter(status="deployed")

    def deployed_with_contract(self):
        return self.deployed().exclude(contract_address__isnull=True).exclude(contract_address="")

    def with_company(self):
        return self.select_related("company")

    def with_market_summary(self):
        from tokens.models import SwapOrder, TransferOrder

        open_orders = TransferOrder.objects.ownership_bound().open().filter(token=OuterRef("pk"))
        last_trade = SwapOrder.objects.filter(share_token=OuterRef("pk"), status=SwapOrderStatus.COMPLETED).order_by(
            "-completed_at"
        )
        return self.annotate(
            best_bid=Subquery(open_orders.buy_orders().order_by("-price_per_share").values("price_per_share")[:1]),
            best_ask=Subquery(open_orders.sell_orders().order_by("price_per_share").values("price_per_share")[:1]),
            last_trade_payment_amount=Subquery(last_trade.values("payment_amount")[:1]),
            last_trade_share_amount=Subquery(last_trade.values("share_amount")[:1]),
            last_trade_decimals=Subquery(last_trade.values("payment_asset__decimals")[:1]),
        )

    def search(self, query):
        if not query:
            return self
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(symbol__icontains=query)
            | models.Q(contract_address__icontains=query)
        )
