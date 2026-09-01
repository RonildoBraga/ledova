from django.db.models import F, Q, QuerySet
from django.db.models.functions import Lower


class TransactionQuerySet(QuerySet):
    def filter_by_wallet(self, wallet):
        if wallet:
            if hasattr(wallet, "uuid"):
                return self.filter(wallet__uuid=wallet.uuid)
            return self.filter(wallet__uuid=wallet)
        return self

    def filter_by_wallets(self, wallets):
        if wallets is not None:
            return self.filter(wallet__in=wallets)
        return self

    def filter_by_asset(self, asset):
        if asset:
            if hasattr(asset, "uuid"):
                return self.filter(asset__uuid=asset.uuid)
            return self.filter(asset__uuid=asset)
        return self

    def filter_by_address(self, address):
        if address:
            return self.filter(Q(from_address__iexact=address) | Q(to_address__iexact=address))
        return self

    def filter_by_date_range(self, start_date=None, end_date=None):
        queryset = self
        if start_date:
            queryset = queryset.filter(block_timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(block_timestamp__lte=end_date)
        return queryset

    def filter_by_direction(self, direction, wallet_uuid=None):
        if direction not in ("incoming", "outgoing"):
            return self

        queryset = self.filter(wallet__uuid=wallet_uuid) if wallet_uuid else self
        if direction == "incoming":
            return queryset.annotate(
                wallet_addr_lower=Lower("wallet__address"), to_addr_lower=Lower("to_address")
            ).filter(to_addr_lower=F("wallet_addr_lower"))
        return queryset.annotate(
            wallet_addr_lower=Lower("wallet__address"), from_addr_lower=Lower("from_address")
        ).filter(from_addr_lower=F("wallet_addr_lower"))

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(wallet__user_account__user_profiles__user=user)

    def with_optimized_data(self):
        return self.select_related("asset", "wallet", "wallet__user_account")

    def for_wallet_address(self, wallet_address):
        return self.filter_by_address(wallet_address)

    def incoming(self, wallet_address):
        if wallet_address:
            return self.filter(to_address__iexact=wallet_address)
        return self

    def outgoing(self, wallet_address):
        if wallet_address:
            return self.filter(from_address__iexact=wallet_address)
        return self

    def latest_transactions(self, limit=20):
        return self.order_by("-block_timestamp")
