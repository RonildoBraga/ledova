from typing import Any, Dict, List

from integrations.blockchain import get_blockchain_client
from shared.constants import SUPPORTED_CHAINS
from wallets.exceptions import InvalidTransactionException


class BalanceService:
    MAX_ADDRESSES_PER_REQUEST = 20

    @staticmethod
    def batch_check_balances(
        addresses: List[str],
        chain: str = "ethereum",
    ) -> Dict[str, Any]:
        if not addresses:
            raise InvalidTransactionException("'addresses' is required and must be a non-empty list.")

        if not isinstance(addresses, list):
            raise InvalidTransactionException("'addresses' must be a list.")

        if len(addresses) > BalanceService.MAX_ADDRESSES_PER_REQUEST:
            raise InvalidTransactionException(
                f"Maximum {BalanceService.MAX_ADDRESSES_PER_REQUEST} addresses allowed per request."
            )

        chain_lower = chain.lower()
        if chain_lower not in SUPPORTED_CHAINS:
            raise InvalidTransactionException(f"Unsupported chain: {chain}. Only ethereum and bitcoin are supported.")

        balances = {}
        errors = []

        for address in addresses:
            try:
                client = get_blockchain_client(chain_lower)
                balance = client.get_native_balance(address)
                balances[address] = str(balance)
            except NotImplementedError:
                errors.append(f"{chain_lower} balance queries require external block explorer APIs")
                break
            except Exception:
                balances[address] = "0"
                errors.append(f"Failed to fetch balance for {address[:8]}...")

        result = {"balances": balances}
        if errors:
            result["errors"] = errors

        return result
