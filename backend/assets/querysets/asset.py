from django.db.models import Q, QuerySet


class AssetQuerySet(QuerySet):
    def filter_by_chain(self, chain):
        if chain:
            return self.filter(chain_deployments__chain__iexact=chain).distinct()
        return self

    def filter_by_supported_chains(self):
        from shared.constants import SUPPORTED_CHAINS

        return self.filter(chain_deployments__chain__in=SUPPORTED_CHAINS).distinct()

    def active(self):
        return self.filter(is_active=True)

    def verified(self):
        """Allowlisted rows; unverified (quarantined) assets never reach a customer."""
        return self.filter(is_verified=True)

    def native_for_chain(self, chain):
        """The chain's native coin: a native_crypto asset with an active contract-less deployment on `chain`."""
        return self.filter(
            asset_type="native_crypto",
            chain_deployments__chain=chain,
            chain_deployments__contract_address__isnull=True,
            chain_deployments__is_active=True,
        ).first()

    def search(self, search_query):
        if not search_query:
            return self
        return self.filter(Q(symbol__icontains=search_query) | Q(name__icontains=search_query))

    def visible_to_user(self, user):
        return self
