import logging
from decimal import Decimal
from typing import Optional

from integrations.blockchain import get_blockchain_client

logger = logging.getLogger(__name__)


def fetch_chain_balance(wallet, asset) -> Optional[Decimal]:
    deployment = asset.get_deployment_for_chain(wallet.chain)
    if deployment is None:
        return None
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
