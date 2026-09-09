from django.db.models import Q, QuerySet

from shared.constants import (
    CHAIN_TO_NATIVE_ASSET,
    NATIVE_ASSET_DECIMALS,
    normalize_chain,
)


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
        return self.filter(is_verified=True)

    def excluding_securities(self):
        return self.exclude(asset_type="tokenized_security")

    def native_for_chain(self, chain):
        chain = normalize_chain(chain)
        symbol = CHAIN_TO_NATIVE_ASSET.get(chain)
        if symbol is None:
            return None
        return self.filter(
            symbol=symbol,
            asset_type="native_crypto",
            is_active=True,
            chain_deployments__chain=chain,
            chain_deployments__contract_address__isnull=True,
            chain_deployments__decimals=NATIVE_ASSET_DECIMALS[symbol],
            chain_deployments__is_active=True,
        ).first()

    def for_chain_and_contract(self, chain, contract_address):
        return self.filter(
            chain_deployments__chain=chain,
            chain_deployments__contract_address__iexact=contract_address,
            chain_deployments__is_active=True,
        ).first()

    def search(self, search_query):
        if not search_query:
            return self
        return self.filter(Q(symbol__icontains=search_query) | Q(name__icontains=search_query))

    def visible_to_user(self, user):
        return self
