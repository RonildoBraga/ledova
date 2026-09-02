from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional


class BlockchainClient(ABC):
    """Network-specific client. Amounts are in standard units (ETH, BTC), never wei or satoshi."""

    @abstractmethod
    def get_native_balance(self, address: str) -> Decimal:
        """Balance in standard units (ETH, BTC)."""

    @abstractmethod
    def get_token_balance(self, address: str, contract_address: str, decimals: int) -> Decimal:
        """Token balance in standard units, scaled by `decimals`."""

    @abstractmethod
    def get_current_block(self) -> int:
        """Latest block height."""

    @abstractmethod
    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Raw transaction dict from the node."""

    @abstractmethod
    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Receipt dict, or None while unconfirmed."""

    @abstractmethod
    def estimate_gas(self, tx_params: Dict[str, Any]) -> int:
        """Estimated gas units for tx_params."""

    @abstractmethod
    def broadcast_transaction(self, signed_tx: str) -> str:
        """Broadcast a signed hex transaction; returns the tx hash."""

    @abstractmethod
    def get_gas_price(self) -> int:
        """Gas price in wei (or the chain's smallest unit)."""

    @abstractmethod
    def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        """Block until the receipt exists; raises TimeoutError after `timeout` seconds."""

    @abstractmethod
    def get_total_supply(self, contract_address: str, decimals: int) -> Decimal:
        """Total supply in standard units, scaled by `decimals`."""

    @abstractmethod
    def get_transaction_history(
        self, address: str, from_block: Optional[int] = None, to_block: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Transactions for an address as dicts with the shared keys:
        tx_hash, from_address, to_address, amount (standard units), block_number,
        block_timestamp (datetime or unix), status ('success'|'failed'), is_error,
        transaction_fee (optional).
        """
