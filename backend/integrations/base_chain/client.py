import json
import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from django.conf import settings
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError, TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams, TxReceipt, Wei

from integrations.base_chain.exceptions import (
    BaseChainConnectionError,
    BaseChainContractError,
    BaseChainTransactionError,
)

logger = logging.getLogger(__name__)

LOG_PREFIX = "[BASE_CHAIN]"


class BaseChainClient:

    _instance: Optional["BaseChainClient"] = None
    _web3: Optional[Web3] = None

    def __new__(cls) -> "BaseChainClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._web3 is None:
            self._connect()

    def _connect(self) -> None:
        rpc_url = getattr(settings, "BLOCKCHAIN_RPC_URL", "http://localhost:8545")

        try:
            self._web3 = Web3(Web3.HTTPProvider(rpc_url))
            self._web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

            chain_id = self._web3.eth.chain_id
            expected_chain_id = settings.BLOCKCHAIN_CHAIN_ID
            if chain_id != expected_chain_id:
                raise BaseChainConnectionError(
                    f"Refusing EVM endpoint on chain {chain_id}; expected chain {expected_chain_id}"
                )
            block_number = self._web3.eth.block_number

            logger.info(f"{LOG_PREFIX} Connected to configured endpoint (chain_id={chain_id}, block={block_number})")

        except BaseChainConnectionError:
            raise
        except Exception as e:
            logger.error(f"{LOG_PREFIX} Failed to connect to configured endpoint ({type(e).__name__})")
            raise BaseChainConnectionError("Failed to connect to configured EVM endpoint") from e

    def assert_expected_chain(self) -> int:
        actual_chain_id = self.w3.eth.chain_id
        expected_chain_id = settings.BLOCKCHAIN_CHAIN_ID
        if actual_chain_id != expected_chain_id:
            raise BaseChainConnectionError(
                f"Refusing EVM endpoint on chain {actual_chain_id}; expected chain {expected_chain_id}"
            )
        return actual_chain_id

    @property
    def w3(self) -> Web3:
        if self._web3 is None:
            self._connect()
        return self._web3

    @property
    def chain_id(self) -> int:
        return self.assert_expected_chain()

    @property
    def block_number(self) -> int:
        return self.w3.eth.block_number

    @property
    def gas_price(self) -> Wei:
        return self.w3.eth.gas_price

    def is_connected(self) -> bool:
        try:
            if self._web3 is None:
                return False
            self._web3.eth.chain_id
            return True
        except Exception:
            return False

    def reconnect(self) -> None:
        self._web3 = None
        self._connect()

    def to_checksum_address(self, address: str) -> ChecksumAddress:
        return self.w3.to_checksum_address(address)

    def is_valid_address(self, address: str) -> bool:
        return self.w3.is_address(address)

    def is_checksum_address(self, address: str) -> bool:
        return self.w3.is_checksum_address(address)

    def to_wei(self, value: Decimal | float | int, unit: str = "ether") -> Wei:
        return self.w3.to_wei(value, unit)

    def from_wei(self, value: Wei, unit: str = "ether") -> Decimal:
        return self.w3.from_wei(value, unit)

    def get_balance(self, address: str) -> Wei:
        checksum_address = self.to_checksum_address(address)
        return self.w3.eth.get_balance(checksum_address)

    def get_balance_ether(self, address: str) -> Decimal:
        return self.from_wei(self.get_balance(address), "ether")

    def get_nonce(self, address: str) -> int:
        checksum_address = self.to_checksum_address(address)
        return self.w3.eth.get_transaction_count(checksum_address, "pending")

    def create_account(self) -> LocalAccount:
        return Account.create()

    def account_from_key(self, private_key: str) -> LocalAccount:
        return Account.from_key(private_key)

    def get_address_from_private_key(self, private_key: str) -> ChecksumAddress:
        account = self.account_from_key(private_key)
        return account.address

    def load_contract_abi(self, contract_name: str) -> list[dict[str, Any]]:
        possible_paths = [
            Path(settings.BASE_DIR).parent
            / "contracts"
            / "artifacts"
            / "contracts"
            / f"{contract_name}.sol"
            / f"{contract_name}.json",
            Path(settings.BASE_DIR).parent / "contracts" / "out" / f"{contract_name}.sol" / f"{contract_name}.json",
            Path(settings.BASE_DIR) / "contracts" / f"{contract_name}.json",
        ]

        for path in possible_paths:
            if path.exists():
                with open(path) as f:
                    artifact = json.load(f)
                    if isinstance(artifact, list):
                        return artifact
                    return artifact.get("abi", artifact)

        raise BaseChainContractError(f"Contract ABI not found for {contract_name}")

    def get_contract(self, address: str, abi: list[dict[str, Any]]) -> Contract:
        checksum_address = self.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum_address, abi=abi)

    def load_contract(self, contract_name: str, address: str) -> Contract:
        abi = self.load_contract_abi(contract_name)
        return self.get_contract(address, abi)

    def build_transaction(
        self,
        contract_function,
        from_address: str,
        value: Wei = Wei(0),
        gas: Optional[int] = None,
        gas_price: Optional[Wei] = None,
        nonce: Optional[int] = None,
    ) -> TxParams:
        checksum_address = self.to_checksum_address(from_address)

        tx: TxParams = {
            "from": checksum_address,
            "chainId": self.chain_id,
            "value": value,
        }

        if nonce is None:
            tx["nonce"] = self.get_nonce(from_address)
        else:
            tx["nonce"] = nonce

        if gas_price is None:
            tx["gasPrice"] = self.gas_price
        else:
            tx["gasPrice"] = gas_price

        tx = contract_function.build_transaction(tx)

        if gas is None:
            try:
                estimated_gas = self.w3.eth.estimate_gas(tx)
                tx["gas"] = int(estimated_gas * 1.2)
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} Gas estimation failed: {e}. Using default.")
                tx["gas"] = 500000
        else:
            tx["gas"] = gas

        return tx

    def sign_transaction(self, tx: TxParams, private_key: str) -> bytes:
        expected_chain_id = self.assert_expected_chain()
        if tx.get("chainId") != expected_chain_id:
            raise BaseChainTransactionError("Refusing to sign a transaction for an unexpected chain")
        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        return signed.raw_transaction

    def send_raw_transaction(self, signed_tx: bytes) -> str:
        self.assert_expected_chain()
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx)
        return tx_hash.hex()

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> TxReceipt:
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

            if receipt["status"] != 1:
                raise BaseChainTransactionError(f"Transaction failed: {tx_hash} (status={receipt['status']})")

            return receipt

        except TransactionNotFound:
            raise BaseChainTransactionError(f"Transaction not found: {tx_hash}")
        except BaseChainTransactionError:
            raise
        except Exception as e:
            raise BaseChainTransactionError(f"Error waiting for receipt: {e}") from e

    def send_transaction(
        self,
        contract_function,
        private_key: str,
        value: Wei = Wei(0),
        gas: Optional[int] = None,
        wait_for_receipt: bool = True,
    ) -> tuple[str, Optional[TxReceipt]]:
        account = self.account_from_key(private_key)

        tx = self.build_transaction(
            contract_function,
            from_address=account.address,
            value=value,
            gas=gas,
        )

        signed_tx = self.sign_transaction(tx, private_key)
        tx_hash = self.send_raw_transaction(signed_tx)

        logger.info(f"{LOG_PREFIX} Transaction sent: {tx_hash}")

        receipt = None
        if wait_for_receipt:
            receipt = self.wait_for_receipt(tx_hash)
            logger.info(
                f"{LOG_PREFIX} Transaction confirmed: {tx_hash} "
                f"(block={receipt['blockNumber']}, gas_used={receipt['gasUsed']})"
            )

        return tx_hash, receipt

    def call_contract_function(self, contract_function) -> Any:
        try:
            return contract_function.call()
        except ContractLogicError as e:
            raise BaseChainContractError(f"Contract call failed: {e}") from e

    def get_block(self, block_identifier: int | str = "latest") -> dict:
        return dict(self.w3.eth.get_block(block_identifier))

    def get_transaction(self, tx_hash: str) -> dict:
        return dict(self.w3.eth.get_transaction(tx_hash))

    def get_transaction_receipt(self, tx_hash: str) -> Optional[TxReceipt]:
        try:
            return self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None


@lru_cache(maxsize=1)
def get_base_chain_client() -> BaseChainClient:
    return BaseChainClient()
