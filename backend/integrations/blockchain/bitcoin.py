"""
Bitcoin blockchain client implementation using Alchemy JSON-RPC.

Bitcoin uses UTXO (Unspent Transaction Output) model. Standard Bitcoin RPC
supports transaction operations but requires address indexing for balance
and history queries.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import base58
import bech32
import requests
from django.conf import settings

from .base import BlockchainClient

logger = logging.getLogger(__name__)


def is_bitcoin_address_valid(address: str, network: str) -> bool:
    """Apply the repository's testnet/regtest-only Bitcoin address policy."""
    if not address:
        return False
    try:
        if network == "test" and address.startswith(("m", "n", "2")):
            payload = base58.b58decode_check(address)
            return len(payload) == 21 and payload[0] in (0x6F, 0xC4)

        expected_hrp = {"test": "tb", "regtest": "bcrt"}.get(network)
        if not expected_hrp:
            return False
        hrp, words = bech32.bech32_decode(address)
        if hrp != expected_hrp or not words or words[0] != 0:
            return False
        witness_program = bech32.convertbits(words[1:], 5, 8, False)
        return witness_program is not None and len(witness_program) in (20, 32)
    except (TypeError, ValueError):
        return False


class BitcoinClient(BlockchainClient):
    """
    Bitcoin blockchain client using Alchemy JSON-RPC provider.

    Supports transaction broadcasting, queries, fee estimation, and address validation.
    Balance and transaction history queries require external block explorer APIs.
    """

    def __init__(self, rpc_url: str, expected_network: str):
        """Initialize a Bitcoin client for an explicit test network."""
        self.rpc_url = rpc_url
        self.expected_network = expected_network
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        try:
            self.assert_expected_network()
            self.get_current_block()
            logger.info("Connected to the approved Bitcoin test endpoint")
        except Exception as e:
            raise ConnectionError("Failed to connect to configured Bitcoin test endpoint") from e

    def assert_expected_network(self) -> str:
        network_info = self._rpc_call("getblockchaininfo")
        actual_network = network_info.get("chain") if isinstance(network_info, dict) else None
        if actual_network != self.expected_network:
            raise ConnectionError(
                f"Refusing Bitcoin endpoint on network {actual_network!r}; expected {self.expected_network!r}"
            )
        return actual_network

    def _rpc_call(self, method: str, params: Optional[List] = None) -> Any:
        """Make JSON-RPC call to Alchemy Bitcoin API."""
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}

        try:
            response = self.session.post(self.rpc_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "error" in data and data["error"]:
                error_msg = data["error"].get("message", "Unknown error")
                error_code = data["error"].get("code", -1)
                raise Exception(f"Bitcoin RPC error ({error_code}): {error_msg}")

            return data.get("result")

        except requests.HTTPError as e:
            logger.error(f"HTTP error calling Bitcoin RPC method '{method}'")
            raise ConnectionError("Bitcoin RPC request failed") from e
        except Exception as e:
            logger.error(f"Error calling Bitcoin RPC method '{method}' ({type(e).__name__})")
            raise ConnectionError("Bitcoin RPC request failed") from e

    def get_current_block(self) -> int:
        """Get latest block height."""
        try:
            block_height = self._rpc_call("getblockcount")
            logger.debug(f"Current block: {block_height}")
            return block_height
        except Exception as e:
            logger.error(f"Error getting current block: {str(e)}")
            raise

    def get_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction details by hash."""
        try:
            tx_data = self._rpc_call("getrawtransaction", [tx_hash, True])
            logger.debug(f"Retrieved transaction: {tx_hash}")
            return tx_data
        except Exception as e:
            logger.error(f"Error getting transaction {tx_hash}: {str(e)}")
            raise

    def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction confirmation status."""
        try:
            tx = self.get_transaction(tx_hash)
            confirmations = tx.get("confirmations", 0)

            if confirmations > 0:
                return {
                    "tx_hash": tx_hash,
                    "confirmed": True,
                    "confirmations": confirmations,
                    "block_height": tx.get("height"),
                    "block_hash": tx.get("blockhash"),
                }
            return None
        except Exception as e:
            logger.error(f"Error getting receipt for {tx_hash}: {str(e)}")
            return None

    def broadcast_transaction(self, signed_tx: str) -> str:
        """Broadcast signed transaction to network."""
        try:
            self.assert_expected_network()
            tx_hash = self._rpc_call("sendrawtransaction", [signed_tx])

            if not tx_hash:
                raise Exception("No transaction hash returned")

            logger.info(f"Transaction broadcasted: {tx_hash}")
            return tx_hash
        except Exception as e:
            logger.error(f"Error broadcasting transaction: {str(e)}")
            raise

    def estimate_gas(self, tx_params: Dict[str, Any]) -> int:
        """
        Estimate transaction fee in satoshis.

        Args:
            tx_params: May include 'conf_target' (blocks) and 'size' (bytes)

        Returns:
            Estimated fee in satoshis
        """
        try:
            conf_target = tx_params.get("conf_target", 6)
            fee_estimate = self._rpc_call("estimatesmartfee", [conf_target])

            if "feerate" in fee_estimate:
                fee_rate_btc_per_kb = Decimal(str(fee_estimate["feerate"]))
                fee_rate_sat_per_byte = (fee_rate_btc_per_kb * Decimal(10**8)) / Decimal(1000)

                tx_size = tx_params.get("size", 250)
                estimated_fee = int(fee_rate_sat_per_byte * tx_size)

                logger.debug(f"Estimated fee: {estimated_fee} satoshis")
                return estimated_fee
            else:
                logger.warning("No feerate available, using default")
                return 5000
        except Exception as e:
            logger.error(f"Error estimating fee: {str(e)}")
            return 5000

    def get_gas_price(self) -> int:
        """Get current fee rate in satoshis per byte."""
        try:
            fee_estimate = self._rpc_call("estimatesmartfee", [6])

            if "feerate" in fee_estimate:
                fee_rate_btc_per_kb = Decimal(str(fee_estimate["feerate"]))
                fee_rate_sat_per_byte = int((fee_rate_btc_per_kb * Decimal(10**8)) / Decimal(1000))
                logger.debug(f"Fee rate: {fee_rate_sat_per_byte} sat/byte")
                return fee_rate_sat_per_byte
            else:
                return 20
        except Exception as e:
            logger.error(f"Error getting fee rate: {str(e)}")
            return 20

    def wait_for_transaction_receipt(self, tx_hash: str, timeout: int = 120) -> Dict[str, Any]:
        """Wait for transaction confirmation."""
        import time

        logger.info(f"Waiting for transaction {tx_hash} confirmation")

        start_time = time.time()
        poll_interval = 10

        while (time.time() - start_time) < timeout:
            receipt = self.get_transaction_receipt(tx_hash)

            if receipt and receipt.get("confirmed"):
                logger.info(f"Transaction confirmed: {tx_hash}")
                return receipt

            time.sleep(poll_interval)

        raise TimeoutError(f"Transaction {tx_hash} not confirmed within {timeout}s")

    def get_native_balance(self, address: str) -> Decimal:
        """Get BTC balance for address using Blockstream API."""
        try:
            blockstream_url = getattr(settings, "BLOCKSTREAM_API_URL", "https://blockstream.info/testnet/api")
            blockstream_timeout = getattr(settings, "BLOCKSTREAM_TIMEOUT", 30)
            url = f"{blockstream_url}/address/{address}"
            response = self.session.get(url, timeout=blockstream_timeout)
            response.raise_for_status()
            data = response.json()

            # Balance in satoshis = funded - spent
            chain_stats = data.get("chain_stats", {})
            funded = Decimal(str(chain_stats.get("funded_txo_sum", 0)))
            spent = Decimal(str(chain_stats.get("spent_txo_sum", 0)))
            balance_satoshis = funded - spent

            # Convert to BTC
            balance_btc = balance_satoshis / Decimal(10**8)
            logger.debug(f"Address {address[:10]}... balance: {balance_btc} BTC")
            return balance_btc

        except Exception as e:
            logger.error(f"Error fetching balance for {address}: {str(e)}")
            raise

    def get_token_balance(self, address: str, contract_address: str, decimals: int) -> Decimal:
        """Get token balance - not supported on Bitcoin."""
        _ = address, contract_address, decimals
        raise NotImplementedError("Bitcoin does not support tokens")

    def get_total_supply(self, contract_address: str, decimals: int) -> Decimal:
        """Get total token supply - not supported on Bitcoin."""
        _ = contract_address, decimals
        raise NotImplementedError("Bitcoin does not support tokens")

    def get_transaction_history(
        self, address: str, from_block: Optional[int] = None, to_block: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get transaction history for address using Blockstream API."""
        try:
            blockstream_url = getattr(settings, "BLOCKSTREAM_API_URL", "https://blockstream.info/testnet/api")
            blockstream_timeout = getattr(settings, "BLOCKSTREAM_TIMEOUT", 30)
            url = f"{blockstream_url}/address/{address}/txs"
            response = self.session.get(url, timeout=blockstream_timeout)
            response.raise_for_status()
            txs = response.json()

            transactions = []
            for tx in txs:
                block_height = tx.get("status", {}).get("block_height")

                if from_block and block_height and block_height < from_block:
                    continue
                if to_block and block_height and block_height > to_block:
                    continue

                tx_hash = tx.get("txid", "")
                block_time_unix = tx.get("status", {}).get("block_time")
                block_timestamp = datetime.fromtimestamp(block_time_unix, tz=timezone.utc) if block_time_unix else None
                is_confirmed = tx.get("status", {}).get("confirmed", False)

                input_value = sum(vin.get("prevout", {}).get("value", 0) for vin in tx.get("vin", []))
                output_value = sum(vout.get("value", 0) for vout in tx.get("vout", []))
                fee_satoshis = input_value - output_value if input_value > output_value else 0
                fee_btc = Decimal(fee_satoshis) / Decimal(10**8)

                address_lower = address.lower()

                sent_amount = Decimal(0)
                for vin in tx.get("vin", []):
                    prevout = vin.get("prevout", {})
                    if prevout.get("scriptpubkey_address", "").lower() == address_lower:
                        sent_amount += Decimal(prevout.get("value", 0))

                received_amount = Decimal(0)
                to_address = None
                for vout in tx.get("vout", []):
                    vout_address = vout.get("scriptpubkey_address", "")
                    if vout_address.lower() == address_lower:
                        received_amount += Decimal(vout.get("value", 0))
                    elif not to_address and vout_address:
                        to_address = vout_address

                if sent_amount > 0:
                    net_amount = -(sent_amount - received_amount) / Decimal(10**8)
                    from_addr = address
                    to_addr = to_address or "unknown"
                else:
                    net_amount = received_amount / Decimal(10**8)
                    from_addr = None
                    for vin in tx.get("vin", []):
                        prevout = vin.get("prevout", {})
                        if prevout.get("scriptpubkey_address"):
                            from_addr = prevout.get("scriptpubkey_address")
                            break
                    from_addr = from_addr or "unknown"
                    to_addr = address

                transactions.append(
                    {
                        "tx_hash": tx_hash,
                        "from_address": from_addr.lower() if from_addr else None,
                        "to_address": to_addr.lower() if to_addr else None,
                        "amount": abs(net_amount),
                        "block_number": block_height,
                        "block_timestamp": block_timestamp,
                        "status": "success" if is_confirmed else "pending",
                        "is_error": False,
                        "transaction_fee": fee_btc,
                        "asset": "BTC",
                        "category": "external",
                    }
                )

            logger.info(f"Fetched {len(transactions)} Bitcoin transactions for {address[:10]}...")
            return transactions

        except Exception as e:
            logger.error(f"Error fetching Bitcoin transaction history for {address}: {str(e)}")
            raise
