"""
Blockchain RPC integration for multi-chain support via Alchemy.

This module provides direct blockchain access for:
- Balance queries (native tokens and ERC20 tokens)
- Transaction monitoring
- Gas estimation
- Transaction broadcasting

Supports:
- Ethereum (via web3.py and Alchemy RPC)
- Bitcoin (via Alchemy Bitcoin API)
"""

from integrations.blockchain.base import BlockchainClient
from integrations.blockchain.bitcoin import BitcoinClient
from integrations.blockchain.ethereum import EthereumClient
from integrations.blockchain.factory import (
    BlockchainClientFactory,
    get_blockchain_client,
)

__all__ = [
    "BlockchainClient",
    "EthereumClient",
    "BitcoinClient",
    "BlockchainClientFactory",
    "get_blockchain_client",
]
