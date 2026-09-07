from dataclasses import dataclass
from typing import Optional

from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction as LegacyTransaction
from eth_account.typed_transactions import TypedTransaction
from eth_utils import to_checksum_address
from hexbytes import HexBytes

TYPED_ENVELOPE_MAX_PREFIX = 0x7F
SUPPORTED_ENVELOPE_TYPES = frozenset({1, 2})


class UnsupportedEnvelopeError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedSignedTransaction:
    sender: str
    to: Optional[str]
    chain_id: Optional[int]
    value: int
    data: bytes
    envelope_type: Optional[int]


def decode_signed_transaction(raw_transaction: bytes) -> DecodedSignedTransaction:
    if not raw_transaction:
        raise ValueError("Empty transaction")

    try:
        if raw_transaction[0] <= TYPED_ENVELOPE_MAX_PREFIX:
            fields = TypedTransaction.from_bytes(HexBytes(raw_transaction)).as_dict()
            chain_id: Optional[int] = int(fields["chainId"])
            envelope_type: Optional[int] = int(fields["type"])
        else:
            fields = LegacyTransaction.from_bytes(raw_transaction).as_dict()
            chain_id = _legacy_chain_id(int(fields["v"]))
            envelope_type = None
        sender = Account.recover_transaction(raw_transaction)
    except Exception as exc:
        raise ValueError("Unable to decode signed transaction") from exc

    if envelope_type is not None and envelope_type not in SUPPORTED_ENVELOPE_TYPES:
        raise UnsupportedEnvelopeError(f"Transaction envelope type {envelope_type} is not supported")

    to = bytes(fields.get("to") or b"")
    return DecodedSignedTransaction(
        sender=sender,
        to=to_checksum_address(to) if to else None,
        chain_id=chain_id,
        value=int(fields.get("value") or 0),
        data=bytes(fields.get("data") or b""),
        envelope_type=envelope_type,
    )


def signer_of(signed_transaction: str) -> str:
    hexadecimal = signed_transaction[2:] if signed_transaction.startswith("0x") else signed_transaction
    return decode_signed_transaction(bytes.fromhex(hexadecimal)).sender


def _legacy_chain_id(v: int) -> Optional[int]:
    if v in (27, 28):
        return None
    return (v - 35) // 2
