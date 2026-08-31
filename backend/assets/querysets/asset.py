from django.db.models import Q, QuerySet


class AssetQuerySet(QuerySet):
    def filter_by_chain(self, chain):
        """Complex: requires distinct()."""
        if chain:
            return self.filter(chain_deployments__chain__iexact=chain).distinct()
        return self

    def filter_by_supported_chains(self):
        from shared.constants import SUPPORTED_CHAINS

        return self.filter(chain_deployments__chain__in=SUPPORTED_CHAINS).distinct()

    def filter_by_contract_address(self, address):
        """Kept for manager proxy."""
        if address:
            return self.filter(chain_deployments__contract_address__iexact=address).distinct()
        return self

    def active(self):
        return self.filter(is_active=True)

    def filter_by_exchange(self, exchange):
        """Complex: inspects object attributes."""
        if exchange:
            if hasattr(exchange, "uuid") and exchange.uuid:
                return self.filter(exchange__uuid=exchange.uuid)
            if hasattr(exchange, "short_name") and exchange.short_name:
                self = self.filter(exchange__short_name=exchange.short_name)
        return self

    def filter_by_price_range(self, min_price=None, max_price=None):
        """Complex: type coercion with error handling."""
        queryset = self

        min_price_value = None
        if min_price is not None:
            try:
                min_price_value = float(min_price)
            except (ValueError, TypeError):
                min_price_value = None

        max_price_value = None
        if max_price is not None:
            try:
                max_price_value = float(max_price)
            except (ValueError, TypeError):
                max_price_value = None

        if min_price_value is not None:
            queryset = queryset.filter(current_price__gte=min_price_value)
        if max_price_value is not None:
            queryset = queryset.filter(current_price__lte=max_price_value)
        return queryset

    def search(self, search_query):
        """Complex: OR query across multiple fields."""
        if not search_query:
            return self
        return self.filter(Q(symbol__icontains=search_query) | Q(name__icontains=search_query))

    def visible_to_user(self, user):
        return self
