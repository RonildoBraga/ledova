from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import UUID

from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from blockchain.tasks import check_pending_transactions

TX_HASH = "0x" + "ab" * 32
OTHER_HASH = "0x" + "cd" * 32
BLOCK_HASH = "0x" + "ef" * 32
RECEIPT = {
    "status": 1,
    "transactionHash": TX_HASH,
    "blockNumber": 77,
    "blockHash": BLOCK_HASH,
    "gasUsed": 21000,
}


def transaction(**changes):
    return BlockchainTransaction.objects.create(
        **{
            "tx_hash": TX_HASH,
            "tx_type": TransactionType.OTHER,
            "status": TransactionStatus.SUBMITTED,
            "from_address": "0x" + "11" * 20,
            "to_address": "0x" + "22" * 20,
            "value": Decimal("1"),
            "gas_limit": 50000,
            "gas_price": Decimal("0.000000001"),
            "nonce": 7,
            "function_name": "syntheticCall",
            "function_args": {"amount": "1"},
            "related_model": "synthetic.Intent",
            "related_uuid": UUID(int=1),
            "submitted_at": timezone.now(),
            "error_message": "Waiting for a receipt",
            **changes,
        }
    )


def stored(tx):
    return BlockchainTransaction.objects.filter(pk=tx.pk).values().get()


def sweep(receipt):
    client = Mock(spec=["get_transaction_receipt"])
    if callable(receipt):
        client.get_transaction_receipt.side_effect = receipt
    else:
        client.get_transaction_receipt.return_value = receipt
    with patch("integrations.base_chain.get_base_chain_client", return_value=client):
        return check_pending_transactions(timestamp=0)
