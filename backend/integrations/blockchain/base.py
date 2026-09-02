"""
Abstract base class for blockchain clients.

Provides a unified interface for interacting with different blockchain networks.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional


class BlockchainClient(ABC):
    """
    Abstract base class for blockchain clients.

    Implementations provide network-specific functionality for:
    - Reading balances (native tokens and smart contract tokens)
    - Querying transaction history
    - Querying individual transactions
    - Broadcasting transactions
    - Monitoring confirmations
    """

    @abstractmethod
    def get_native_balance(self, address: str) -> Decimal:
        """
        Get native token balance (BTC, ETH, etc.)

        Args:
            address: Blockchain address to query

        Returns:
            Balance in standard units (BTC, ETH, not satoshi/wei)
        """

    @abstractmethod
    def get_token_balance(self, address: str, contract_address: str, decimals: int) -> Decimal:
        """
        Get ERC20/token balance

        Args:
            address: Wallet address to query
            contract_address: Token contract address
            decimals: Token decimals

        Returns:
            Balance in standard units (not base units)
        """

    @abstractmethod
    def get_current_block(self) -> int:
        """
        Get latest block number

        Returns:
            Current block height/number
        """

    @abstractmethod
    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get transaction details

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction data dictionary
        """

    @abstractmethod
    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get transaction receipt (confirmation status)

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction receipt dictionary, or None if not yet confirmed
        """

    @abstractmethod
    def estimate_gas(self, tx_params: Dict[str, Any]) -> int:
        """
        Estimate gas for transaction

        Args:
            tx_params: Transaction parameters

        Returns:
            Estimated gas units
        """

    @abstractmethod
    def broadcast_transaction(self, signed_tx: str) -> str:
        """
        Broadcast signed transaction to network

        Args:
            signed_tx: Signed transaction data (hex string)

        Returns:
            Transaction hash
        """

    @abstractmethod
    def get_gas_price(self) -> int:
        """
        Get current gas price

        Returns:
            Gas price in wei (or smallest unit)
        """

    @abstractmethod
    def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        """
        Wait for transaction to be confirmed

        Args:
            tx_hash: Transaction hash
            timeout: Maximum wait time in seconds

        Returns:
            Transaction receipt

        Raises:
            TimeoutError: If transaction not confirmed within timeout
        """

    @abstractmethod
    def get_total_supply(self, contract_address: str, decimals: int) -> Decimal:
        """
        Get total token supply for an ERC20 contract.

        Args:
            contract_address: Token contract address
            decimals: Token decimals

        Returns:
            Total supply in standard units (not base units)
        """

    @abstractmethod
    def get_transaction_history(
        self, address: str, from_block: Optional[int] = None, to_block: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get transaction history for an address

        Args:
            address: Blockchain address to query
            from_block: Starting block number (optional)
            to_block: Ending block number (optional)

        Returns:
            List of transaction dictionaries with standardized fields:
            - tx_hash: Transaction hash
            - from_address: Sender address
            - to_address: Recipient address
            - amount: Transaction amount in standard units
            - block_number: Block number
            - block_timestamp: Timestamp (datetime or unix timestamp)
            - status: 'success' or 'failed'
            - is_error: Boolean indicating if transaction failed
            - transaction_fee: Fee paid (optional)
        """
