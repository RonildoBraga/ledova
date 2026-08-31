import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from integrations.blockchain import get_blockchain_client
from shared.constants import normalize_chain
from shared.utils.logging_utils import LoggingContext
from wallets.exceptions import BlockchainAPIError

logger = logging.getLogger("ledova_backend")


def fetch_wallet_transactions(
    wallet,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    chain = normalize_chain(wallet.chain)

    try:
        client = get_blockchain_client(chain)
        transactions = client.get_transaction_history(wallet.address)

        for tx in transactions:
            tx["chain"] = chain

        if start_date or end_date:
            transactions = _filter_transactions_by_date(transactions, start_date, end_date)

        return transactions

    except Exception as e:
        logger.error(f"{LoggingContext.WALLET_TRANSACTIONS} Error: {e}")
        raise BlockchainAPIError(f"Failed to fetch transactions: {e}")


def _filter_transactions_by_date(
    transactions: List[Dict[str, Any]],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    filtered = []

    for tx in transactions:
        tx_timestamp = tx.get("block_timestamp")
        if not tx_timestamp or not isinstance(tx_timestamp, datetime):
            continue

        if start_date and tx_timestamp < start_date:
            continue
        if end_date and tx_timestamp > end_date:
            continue

        filtered.append(tx)

    return filtered
