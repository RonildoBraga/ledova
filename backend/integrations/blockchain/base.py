from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional


class BlockchainClient(ABC):

    @abstractmethod
    def get_native_balance(self, address: str) -> Decimal:
        pass

    @abstractmethod
    def get_token_balance(self, address: str, contract_address: str, decimals: int) -> Decimal:
        pass

    @abstractmethod
    def get_current_block(self) -> int:
        pass

    @abstractmethod
    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def estimate_gas(self, tx_params: Dict[str, Any]) -> int:
        pass

    @abstractmethod
    def broadcast_transaction(self, signed_tx: str) -> str:
        pass

    @abstractmethod
    def get_gas_price(self) -> int:
        pass

    @abstractmethod
    def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_total_supply(self, contract_address: str, decimals: int) -> Decimal:
        pass

    @abstractmethod
    def get_transaction_history(
        self, address: str, from_block: Optional[int] = None, to_block: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        pass
