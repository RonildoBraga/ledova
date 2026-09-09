from unittest.mock import Mock

from eth_account import Account

from blockchain.services.outgoing import (
    open_operation,
    prepare_operation,
    sign_operation,
)
from integrations.base_chain.client import BaseChainClient

KEY = "0x" + "11" * 32
SENDER = Account.from_key(KEY).address
TARGET = "0x" + "aa" * 20
CHAIN_ID = 31337
BLOCK_HASH = "0x" + "bb" * 32


def chain_client():
    client = Mock(spec=BaseChainClient)
    client.assert_expected_chain.return_value = CHAIN_ID
    client.get_nonce.return_value = 7
    client.gas_price = 10**9
    client.estimate_gas.return_value = 60000
    client.get_transaction_receipt.return_value = None
    return client


def claim_operation(key="synthetic:1", **changes):
    intent = {"chain_id": CHAIN_ID, "sender": SENDER, "to": TARGET, "value": 3, "data": "0x1234"}
    return open_operation(key, **(intent | changes))


def sign_claim(claim, client=None, key=KEY):
    client = client or chain_client()
    return sign_operation(claim, prepare_operation(claim, client), key)


def receipt(attempt, status=1):
    return {
        "transactionHash": attempt.tx_hash,
        "status": status,
        "blockNumber": 12,
        "blockHash": BLOCK_HASH,
        "gasUsed": 21000,
    }
