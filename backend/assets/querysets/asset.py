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

    def active(self):
        return self.filter(is_active=True)

    def search(self, search_query):
        """Complex: OR query across multiple fields."""
        if not search_query:
            return self
        return self.filter(Q(symbol__icontains=search_query) | Q(name__icontains=search_query))

    def visible_to_user(self, user):
        return self
