from collections.abc import Mapping
from datetime import datetime
from datetime import timezone as datetime_timezone
from decimal import Decimal, localcontext
from typing import Any, Callable, Dict, NamedTuple, Optional

from integrations.blockchain.receipts import (
    nonnegative_integer,
    normalized_hash,
    transaction_hash_matches,
)
from shared.constants import BLOCKCHAIN_BITCOIN, EVM_BLOCKCHAINS

MAX_BLOCK_NUMBER = 2**63 - 1
MAX_EVM_QUANTITY = 2**256 - 1


def _receipt_field(receipt, primary, alias):
    return receipt.get(primary) if primary in receipt else receipt.get(alias)


def extract_actual_fee(receipt: Dict[str, Any], chain: str) -> Optional[Decimal]:
    if chain.lower() in EVM_BLOCKCHAINS:
        gas_used = nonnegative_integer(
            _receipt_field(receipt, "gasUsed", "gas_used"), maximum=MAX_EVM_QUANTITY, encoded=True
        )
        gas_price = nonnegative_integer(
            _receipt_field(receipt, "effectiveGasPrice", "effective_gas_price"),
            maximum=MAX_EVM_QUANTITY,
            encoded=True,
        )
        if gas_used is None or gas_price is None:
            return None
        raw_fee, decimals = gas_used * gas_price, 18
    elif chain.lower() == BLOCKCHAIN_BITCOIN:
        raw_fee, decimals = nonnegative_integer(receipt.get("fee"), maximum=10**20 - 1), 8
    else:
        return None
    if raw_fee is None or raw_fee >= 10 ** (12 + decimals):
        return None
    with localcontext() as context:
        context.prec = 30
        return Decimal(raw_fee).scaleb(-decimals)


class _ReceiptReader(NamedTuple):

    block_number: Callable[[Dict[str, Any]], Optional[int]]
    succeeded: Callable[[Dict[str, Any]], Optional[bool]]
    block_timestamp: Callable[[Any, Dict[str, Any], Optional[int]], Optional[datetime]]
    block_hash: Callable[[Dict[str, Any]], Optional[str]]


def _evm_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return nonnegative_integer(
        _receipt_field(receipt, "blockNumber", "block_number"), maximum=MAX_BLOCK_NUMBER, encoded=True
    )


def _evm_block_hash(receipt):
    value = normalized_hash(_receipt_field(receipt, "blockHash", "block_hash"))
    return "0x" + value if value is not None else None


def _block_time(seconds, *, encoded=False):
    seconds = nonnegative_integer(seconds, maximum=253402300799, encoded=encoded)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=datetime_timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _evm_succeeded(receipt: Dict[str, Any]) -> Optional[bool]:
    status = receipt.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or status not in (0, 1):
        return None
    return status == 1


def _evm_block_timestamp(client: Any, receipt: Dict[str, Any], block_number: Optional[int]) -> Optional[datetime]:
    block_hash = _evm_block_hash(receipt)
    if block_hash is None or block_number is None or not hasattr(client, "w3"):
        return None
    try:
        block = client.w3.eth.get_block(block_hash)
        if (
            not isinstance(block, Mapping)
            or not transaction_hash_matches(block.get("hash"), block_hash)
            or nonnegative_integer(block.get("number"), maximum=MAX_BLOCK_NUMBER, encoded=True) != block_number
        ):
            return None
        return _block_time(block.get("timestamp"), encoded=True)
    except Exception:
        return None


def _bitcoin_block_number(receipt: Dict[str, Any]) -> Optional[int]:
    return nonnegative_integer(receipt.get("block_height"), maximum=MAX_BLOCK_NUMBER)


def _bitcoin_block_hash(receipt):
    return normalized_hash(receipt.get("block_hash"))


def _bitcoin_succeeded(receipt: Dict[str, Any]) -> Optional[bool]:
    confirmations = receipt.get("confirmations")
    if (
        receipt.get("confirmed") is True
        and isinstance(confirmations, int)
        and not isinstance(confirmations, bool)
        and confirmations > 0
    ):
        return True
    return None


def _bitcoin_block_timestamp(client: Any, receipt: Dict[str, Any], block_number: Optional[int]) -> Optional[datetime]:
    block_hash = _bitcoin_block_hash(receipt)
    if block_hash is None or block_number is None or not hasattr(client, "get_block_timestamp"):
        return None
    try:
        seconds = client.get_block_timestamp(block_hash, expected_height=block_number)
    except Exception:
        return None
    return _block_time(seconds)


_EVM_RECEIPT_READER = _ReceiptReader(_evm_block_number, _evm_succeeded, _evm_block_timestamp, _evm_block_hash)

_RECEIPT_READERS = {
    BLOCKCHAIN_BITCOIN: _ReceiptReader(
        _bitcoin_block_number, _bitcoin_succeeded, _bitcoin_block_timestamp, _bitcoin_block_hash
    ),
}


def get_receipt_reader(chain: str) -> _ReceiptReader:
    return _RECEIPT_READERS.get(chain.lower(), _EVM_RECEIPT_READER)
