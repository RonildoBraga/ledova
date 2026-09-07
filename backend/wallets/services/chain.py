import logging
from decimal import Decimal
from typing import Optional

from assets.models import AssetType
from integrations.blockchain import get_blockchain_client

logger = logging.getLogger(__name__)

NO_CONTRACT_ADDRESS = "{symbol} has no contract address on {chain}; its balance stays unknown"
NOT_A_SHARE_CLASS = (
    "{symbol} at {address} on {chain} is not a share class this deployment issued; its balance stays unknown"
)


def fetch_chain_balance(wallet, asset) -> Optional[Decimal]:
    deployment = asset.get_deployment_for_chain(wallet.chain)
    if deployment is None:
        return None
    if not deployment.contract_address and asset.asset_type != AssetType.NATIVE_CRYPTO.value:
        logger.warning(NO_CONTRACT_ADDRESS.format(symbol=asset.symbol, chain=wallet.chain))
        return None
    if asset.asset_type == AssetType.TOKENIZED_SECURITY.value:
        return _share_balance(wallet, asset, deployment)
    try:
        client = get_blockchain_client(wallet.chain)
        if deployment.contract_address:
            return client.get_token_balance(
                address=wallet.address,
                contract_address=deployment.contract_address,
                decimals=deployment.decimals,
            )
        return client.get_native_balance(wallet.address)
    except Exception as e:
        logger.warning(f"Balance query failed for {asset.symbol} on {wallet.chain}: {e}")
        return None


def _share_balance(wallet, asset, deployment) -> Optional[Decimal]:
    from tokens.models import ShareToken
    from tokens.services.share_token_service import ShareTokenService

    token = ShareToken.objects.deployed_at(deployment.chain, deployment.contract_address).first()
    if token is None:
        logger.warning(
            NOT_A_SHARE_CLASS.format(symbol=asset.symbol, address=deployment.contract_address, chain=deployment.chain)
        )
        return None
    try:
        return Decimal(ShareTokenService().get_token_balance(token.contract_address, wallet.address))
    except Exception as e:
        logger.warning(f"Balance query failed for {asset.symbol} on {wallet.chain}: {e}")
        return None
