from typing import Optional

from assets.models import Asset, AssetChainDeployment
from operators.exceptions import SettlementAssetNotDeployedException
from operators.models import Operator

NOT_DEPLOYED = "{symbol} has no active deployment with a contract address on {chain}."


def live_deployments(chain: str):
    return (
        AssetChainDeployment.objects.filter(chain=chain, is_active=True)
        .exclude(contract_address__isnull=True)
        .exclude(contract_address="")
    )


def deployment_on_chain(asset, chain: str) -> Optional[AssetChainDeployment]:
    if asset is None:
        return None
    return live_deployments(chain).filter(asset=asset).first()


def deployment_for(asset) -> Optional[AssetChainDeployment]:
    return deployment_on_chain(asset, Operator.get().receiving_wallet_chain)


def require_deployment(asset) -> AssetChainDeployment:
    operator = Operator.get()
    deployment = deployment_on_chain(asset, operator.receiving_wallet_chain)
    if deployment is None:
        raise SettlementAssetNotDeployedException(
            NOT_DEPLOYED.format(symbol=asset.symbol if asset else "?", chain=operator.receiving_wallet_chain)
        )
    return deployment


def settlement_deployments():
    operator = Operator.get()
    return (
        live_deployments(operator.receiving_wallet_chain)
        .filter(asset__is_active=True, asset__in=operator.supported_settlement_assets.all())
        .select_related("asset")
    )


def settlement_assets():
    return Asset.objects.filter(pk__in=settlement_deployments().values("asset_id"))
