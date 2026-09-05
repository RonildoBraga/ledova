import logging

from django.conf import settings

from shared.constants import (
    BLOCKCHAIN_BASE,
    BLOCKCHAIN_BITCOIN,
    BLOCKCHAIN_ETHEREUM,
    normalize_chain,
)

from .base import BlockchainClient
from .bitcoin import BitcoinClient
from .ethereum import EthereumClient

logger = logging.getLogger(__name__)


class BlockchainClientFactory:

    _clients = {}

    @classmethod
    def get_client(cls, chain: str, use_cache: bool = True) -> BlockchainClient:
        normalized_chain = normalize_chain(chain)
        supported = (BLOCKCHAIN_ETHEREUM, BLOCKCHAIN_BITCOIN, BLOCKCHAIN_BASE)
        if normalized_chain not in supported:
            raise ValueError(f"Unsupported blockchain: {chain}. Supported chains: ethereum (eth), bitcoin (btc), base")

        if use_cache and normalized_chain in cls._clients:
            logger.debug(f"Returning cached {normalized_chain} client")
            return cls._clients[normalized_chain]

        if normalized_chain == BLOCKCHAIN_ETHEREUM:
            alchemy_url = getattr(settings, "ALCHEMY_ETH_URL", None)
            if not alchemy_url:
                raise AttributeError("ALCHEMY_ETH_URL must be set to an approved Ethereum testnet RPC endpoint")
            client = EthereumClient(
                alchemy_url,
                settings.ETHEREUM_CHAIN_ID,
                asset_transfer_history_enabled=settings.EVM_ASSET_TRANSFER_HISTORY_ENABLED,
            )
        elif normalized_chain == BLOCKCHAIN_BASE:
            base_url = getattr(settings, "BLOCKCHAIN_RPC_URL", None) or getattr(settings, "ALCHEMY_BASE_URL", None)
            if not base_url:
                raise AttributeError("BLOCKCHAIN_RPC_URL must be set to an approved Base testnet or local RPC endpoint")
            client = EthereumClient(
                base_url,
                settings.BLOCKCHAIN_CHAIN_ID,
                asset_transfer_history_enabled=settings.EVM_ASSET_TRANSFER_HISTORY_ENABLED,
            )
        elif normalized_chain == BLOCKCHAIN_BITCOIN:
            alchemy_url = getattr(settings, "ALCHEMY_BTC_URL", None)
            if not alchemy_url:
                raise AttributeError("ALCHEMY_BTC_URL must be set to an approved Bitcoin testnet RPC endpoint")
            client = BitcoinClient(alchemy_url, settings.BITCOIN_NETWORK)
        else:
            raise ValueError(f"Unsupported blockchain: {chain}. Supported chains: ethereum (eth), bitcoin (btc), base")

        if use_cache:
            cls._clients[normalized_chain] = client
            logger.info(f"Created and cached {normalized_chain} client")

        return client


def get_blockchain_client(chain: str) -> BlockchainClient:
    return BlockchainClientFactory.get_client(chain)
