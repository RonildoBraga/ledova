from decimal import Decimal, InvalidOperation

from django.conf import settings
from rest_framework.exceptions import NotFound
from web3 import Web3

from integrations.blockchain import get_blockchain_client
from integrations.blockchain.bitcoin import is_bitcoin_address_valid
from shared.constants import BLOCKCHAIN_BITCOIN, SUPPORTED_CHAINS
from users.models import UserAccount
from wallets.exceptions import InvalidTransactionException


class BalanceService:
    MAX_ADDRESSES_PER_REQUEST = 20

    @staticmethod
    def batch_check_balances(user, *, user_account, addresses, chain):
        if not UserAccount.objects.accounts_the_user_is_a_member_of(user).filter(pk=user_account).exists():
            raise NotFound("Account not found.")
        if chain not in SUPPORTED_CHAINS:
            raise InvalidTransactionException("Select a supported wallet network.")
        if not isinstance(addresses, list) or not 1 <= len(addresses) <= BalanceService.MAX_ADDRESSES_PER_REQUEST:
            raise InvalidTransactionException("Provide between 1 and 20 wallet addresses.")
        for address in addresses:
            valid = isinstance(address, str) and (
                is_bitcoin_address_valid(address, settings.BITCOIN_NETWORK)
                if chain == BLOCKCHAIN_BITCOIN
                else Web3.is_address(address)
            )
            if not valid:
                raise InvalidTransactionException("Every address must belong to the selected test network.")

        balances = dict.fromkeys(addresses)
        errors = []
        try:
            client = get_blockchain_client(chain)
        except Exception:
            errors.append("Balance provider unavailable. Try again later.")
        else:
            for address in balances:
                try:
                    balance = Decimal(client.get_native_balance(address))
                    if not balance.is_finite() or balance < 0:
                        raise InvalidOperation
                    balances[address] = str(balance)
                except Exception:
                    errors.append("A balance could not be read. Try again later.")
        result = {"user_account": str(user_account), "chain": chain, "balances": balances}
        if errors:
            result["errors"] = list(dict.fromkeys(errors))
        return result
