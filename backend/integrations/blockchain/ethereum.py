import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
from django.utils.dateparse import parse_datetime
from web3 import Web3
from web3.exceptions import TimeExhausted, TransactionNotFound

from .base import BlockchainClient

logger = logging.getLogger(__name__)


class EthereumClient(BlockchainClient):

    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_to", "type": "address"},
                {"name": "_value", "type": "uint256"},
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function",
        },
    ]

    ERC20_DEFAULT_GAS_LIMIT = 80000

    def __init__(self, rpc_url: str, expected_chain_id: int, *, asset_transfer_history_enabled: bool = False):
        self.rpc_url = rpc_url
        self.expected_chain_id = expected_chain_id
        self.asset_transfer_history_enabled = asset_transfer_history_enabled
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to configured EVM endpoint")

        chain_id = self.assert_expected_chain()
        logger.info(f"Connected to approved EVM chain (chain_id={chain_id})")

    def assert_expected_chain(self) -> int:
        actual_chain_id = self.w3.eth.chain_id
        if actual_chain_id != self.expected_chain_id:
            raise ConnectionError(
                f"Refusing EVM endpoint on chain {actual_chain_id}; expected chain {self.expected_chain_id}"
            )
        return actual_chain_id

    def get_native_balance(self, address: str) -> Decimal:
        try:
            checksum_address = Web3.to_checksum_address(address)
            balance_wei = self.w3.eth.get_balance(checksum_address)
            balance_eth = Decimal(balance_wei) / Decimal(10**18)
            logger.debug(f"ETH balance for {address}: {balance_eth}")
            return balance_eth
        except Exception as e:
            logger.error(f"Error getting ETH balance for {address}: {str(e)}")
            raise

    def get_token_balance(self, address: str, contract_address: str, decimals: int) -> Decimal:
        try:
            checksum_address = Web3.to_checksum_address(address)
            checksum_contract = Web3.to_checksum_address(contract_address)

            contract = self.w3.eth.contract(address=checksum_contract, abi=self.ERC20_ABI)

            balance_base = contract.functions.balanceOf(checksum_address).call()
            balance_standard = Decimal(balance_base) / Decimal(10**decimals)

            logger.debug(f"Token balance for {address}: {balance_standard}")
            return balance_standard

        except Exception as e:
            logger.error(f"Error getting token balance for {address}: {str(e)}")
            raise

    def get_total_supply(self, contract_address: str, decimals: int) -> Decimal:
        try:
            checksum_contract = Web3.to_checksum_address(contract_address)
            contract = self.w3.eth.contract(address=checksum_contract, abi=self.ERC20_ABI)
            raw_supply = contract.functions.totalSupply().call()
            supply = Decimal(raw_supply) / Decimal(10**decimals)
            logger.debug(f"Total supply for {contract_address}: {supply}")
            return supply
        except Exception as e:
            logger.error(f"Error getting total supply for {contract_address}: {e}")
            raise

    def get_current_block(self) -> int:
        try:
            block_number = self.w3.eth.block_number
            logger.debug(f"Current block: {block_number}")
            return block_number
        except Exception as e:
            logger.error(f"Error getting current block: {str(e)}")
            raise

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            return dict(tx)
        except TransactionNotFound:
            logger.warning(f"Transaction not found: {tx_hash}")
            raise
        except Exception as e:
            logger.error(f"Error getting transaction {tx_hash}: {str(e)}")
            raise

    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            return dict(receipt)
        except TransactionNotFound:
            logger.debug(f"Receipt not yet available: {tx_hash}")
            return None
        except Exception as e:
            logger.error(f"Error getting receipt for {tx_hash}: {str(e)}")
            raise

    def estimate_gas(self, tx_params: Dict[str, Any]) -> int:
        try:
            if "from" in tx_params:
                tx_params["from"] = Web3.to_checksum_address(tx_params["from"])
            if "to" in tx_params:
                tx_params["to"] = Web3.to_checksum_address(tx_params["to"])

            gas_estimate = self.w3.eth.estimate_gas(tx_params)
            logger.debug(f"Gas estimate: {gas_estimate}")
            return gas_estimate

        except Exception as e:
            logger.error(f"Error estimating gas: {str(e)}")
            raise

    def broadcast_transaction(self, signed_tx: str) -> str:
        try:
            self.assert_expected_chain()
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx)
            tx_hash_hex = tx_hash.hex()
            logger.info(f"Transaction broadcasted: {tx_hash_hex}")
            return tx_hash_hex

        except Exception as e:
            logger.error(f"Error broadcasting transaction: {str(e)}")
            raise

    def get_gas_price(self) -> int:
        try:
            gas_price = self.w3.eth.gas_price
            logger.debug(f"Gas price: {gas_price} wei")
            return gas_price
        except Exception as e:
            logger.error(f"Error getting gas price: {str(e)}")
            raise

    def is_address_valid(self, address: str) -> bool:
        return self.w3.is_address(address)

    def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        try:
            logger.info(f"Waiting for transaction {tx_hash} confirmation")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            logger.info(f"Transaction confirmed: {tx_hash}")
            return dict(receipt)

        except TimeExhausted:
            logger.error(f"Timeout waiting for {tx_hash} after {timeout}s")
            raise TimeoutError(f"Transaction not confirmed within {timeout}s")
        except Exception as e:
            logger.error(f"Error waiting for receipt {tx_hash}: {str(e)}")
            raise

    def get_token_info(self, contract_address: str) -> Dict[str, Any]:
        try:
            checksum_contract = Web3.to_checksum_address(contract_address)
            contract = self.w3.eth.contract(address=checksum_contract, abi=self.ERC20_ABI)

            symbol = contract.functions.symbol().call()
            decimals = contract.functions.decimals().call()

            logger.debug(f"Token info: {symbol}, {decimals} decimals")

            return {"symbol": symbol, "decimals": decimals, "contract_address": contract_address}

        except Exception as e:
            logger.error(f"Error getting token info for {contract_address}: {str(e)}")
            raise

    def build_erc20_transfer_data(self, contract_address: str, recipient: str, amount: Decimal, decimals: int) -> str:
        try:
            checksum_contract = Web3.to_checksum_address(contract_address)
            checksum_recipient = Web3.to_checksum_address(recipient)

            contract = self.w3.eth.contract(address=checksum_contract, abi=self.ERC20_ABI)

            amount_base_units = int(amount * Decimal(10**decimals))

            encoded_data = contract.encode_abi(
                abi_element_identifier="transfer", args=[checksum_recipient, amount_base_units]
            )

            logger.debug(f"Built ERC-20 transfer data: {len(encoded_data)} bytes")
            return encoded_data

        except Exception as e:
            logger.error(f"Error building ERC-20 transfer data: {str(e)}")
            raise

    def estimate_erc20_transfer_gas(
        self, from_address: str, contract_address: str, recipient: str, amount: Decimal, decimals: int
    ) -> int:
        try:
            checksum_from = Web3.to_checksum_address(from_address)
            checksum_contract = Web3.to_checksum_address(contract_address)

            encoded_data = self.build_erc20_transfer_data(contract_address, recipient, amount, decimals)

            tx_params = {
                "from": checksum_from,
                "to": checksum_contract,
                "data": encoded_data,
                "value": 0,
            }

            gas_estimate = self.w3.eth.estimate_gas(tx_params)
            gas_with_buffer = int(gas_estimate * 1.2)

            logger.debug(f"ERC-20 gas estimate: {gas_estimate}, with buffer: {gas_with_buffer}")
            return gas_with_buffer

        except Exception as e:
            logger.warning(f"Gas estimation failed, using default: {str(e)}")
            return self.ERC20_DEFAULT_GAS_LIMIT

    def get_nonce(self, address: str) -> int:
        try:
            checksum_address = Web3.to_checksum_address(address)
            nonce = self.w3.eth.get_transaction_count(checksum_address, "pending")
            logger.debug(f"Nonce for {address}: {nonce}")
            return nonce
        except Exception as e:
            logger.error(f"Error getting nonce for {address}: {str(e)}")
            raise

    def get_transaction_history(
        self, address: str, from_block: Optional[int] = None, to_block: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not self.asset_transfer_history_enabled:
            return []

        try:
            checksum_address = Web3.to_checksum_address(address)

            from_block_hex = hex(from_block) if from_block else "0x0"
            to_block_param = hex(to_block) if to_block else "latest"

            logger.debug(f"Fetching history for {checksum_address}")

            transactions = []

            outgoing = self._fetch_asset_transfers(
                from_address=checksum_address, from_block=from_block_hex, to_block=to_block_param
            )
            transactions.extend(outgoing)

            incoming = self._fetch_asset_transfers(
                to_address=checksum_address, from_block=from_block_hex, to_block=to_block_param
            )
            transactions.extend(incoming)

            seen_hashes = set()
            unique_transactions = []
            for tx in sorted(transactions, key=lambda x: x["block_number"], reverse=True):
                if tx["tx_hash"] not in seen_hashes:
                    seen_hashes.add(tx["tx_hash"])
                    unique_transactions.append(tx)

            logger.info(f"Fetched {len(unique_transactions)} transactions")

            return unique_transactions

        except Exception as e:
            logger.error(f"Error fetching history for {address}: {str(e)}")
            raise

    def _fetch_asset_transfers(
        self,
        from_address: Optional[str] = None,
        to_address: Optional[str] = None,
        from_block: str = "0x0",
        to_block: str = "latest",
    ) -> List[Dict[str, Any]]:
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getAssetTransfers",
                "params": [
                    {
                        "fromBlock": from_block,
                        "toBlock": to_block,
                        "category": ["external", "internal", "erc20", "erc721", "erc1155"],
                        "withMetadata": True,
                        "excludeZeroValue": True,
                        "maxCount": "0x3e8",
                    }
                ],
            }

            if from_address:
                payload["params"][0]["fromAddress"] = from_address
            if to_address:
                payload["params"][0]["toAddress"] = to_address

            response = requests.post(
                self.rpc_url, json=payload, headers={"Content-Type": "application/json"}, timeout=30
            )
            response.raise_for_status()

            data = response.json()

            if "error" in data:
                raise Exception(f"Alchemy API error: {data['error']}")

            transfers = data.get("result", {}).get("transfers", [])

            standardized_transfers = []
            for transfer in transfers:
                tx_hash = transfer.get("hash", "")

                gas_fee = None
                try:
                    receipt = self.get_transaction_receipt(tx_hash)
                    if receipt and "gasUsed" in receipt and "effectiveGasPrice" in receipt:
                        gas_used = receipt["gasUsed"]
                        effective_gas_price = receipt["effectiveGasPrice"]
                        gas_fee_wei = gas_used * effective_gas_price
                        gas_fee = Decimal(gas_fee_wei) / Decimal(10**18)
                except Exception as e:
                    logger.debug(f"Could not fetch gas fee for {tx_hash}: {e}")

                raw_contract = transfer.get("rawContract", {})
                contract_address = raw_contract.get("address")
                token_decimals = None
                if raw_contract.get("decimal"):
                    try:
                        token_decimals = int(raw_contract.get("decimal"), 16)
                    except (ValueError, TypeError):
                        pass

                standardized_transfers.append(
                    {
                        "tx_hash": tx_hash,
                        "from_address": transfer.get("from", "").lower(),
                        "to_address": transfer.get("to", "").lower() if transfer.get("to") else None,
                        "amount": Decimal(str(transfer.get("value", 0))),
                        "block_number": int(transfer.get("blockNum", "0x0"), 16),
                        "block_timestamp": parse_datetime(transfer.get("metadata", {}).get("blockTimestamp", "")),
                        "status": "success",
                        "is_error": False,
                        "transaction_fee": gas_fee,
                        "asset": transfer.get("asset", "ETH"),
                        "category": transfer.get("category", "external"),
                        "contract_address": contract_address.lower() if contract_address else None,
                        "token_decimals": token_decimals,
                    }
                )

            return standardized_transfers

        except Exception as e:
            logger.error(f"Error fetching asset transfers: {str(e)}")
            return []
