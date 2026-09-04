import logging
from decimal import Decimal
from typing import Optional

from integrations.blockchain import get_blockchain_client

logger = logging.getLogger(__name__)


def fetch_chain_balance(wallet, asset) -> Optional[Decimal]:
    """On-chain balance of `asset` for `wallet` on the wallet's own chain.

    None when the asset has no active deployment on that chain or the RPC call fails,
    so callers keep the stored holding instead of overwriting it.
    """
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
